use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent, State};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Clone)]
struct ApiState {
    inner: Arc<(Mutex<Option<Result<String, String>>>, Condvar)>,
    error_shown: Arc<AtomicBool>,
}

impl ApiState {
    fn new() -> Self {
        Self {
            inner: Arc::new((Mutex::new(None), Condvar::new())),
            error_shown: Arc::new(AtomicBool::new(false)),
        }
    }

    fn set_result(&self, res: Result<String, String>) {
        let (lock, cvar) = &*self.inner;
        if let Ok(mut guard) = lock.lock() {
            if guard.is_none() {
                *guard = Some(res);
                cvar.notify_all();
            }
        }
    }

    fn wait_ready(&self, timeout: Duration) -> Result<String, String> {
        let (lock, cvar) = &*self.inner;
        let deadline = Instant::now() + timeout;
        let mut guard = lock
            .lock()
            .map_err(|_| "Internal API state lock poisoned".to_string())?;
        while guard.is_none() {
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err("Timed out waiting for Veraxi API sidecar readiness (30s).".to_string());
            }
            let (next_guard, wait_res) = cvar
                .wait_timeout(guard, remaining)
                .map_err(|_| "Internal API state wait failed".to_string())?;
            guard = next_guard;
            if wait_res.timed_out() && guard.is_none() {
                return Err("Timed out waiting for Veraxi API sidecar readiness (30s).".to_string());
            }
        }
        guard
            .clone()
            .unwrap_or_else(|| Err("Unknown sidecar state".to_string()))
    }
}

fn show_startup_error_once(app: &tauri::AppHandle, state: &ApiState, err: &str) {
    if !state.error_shown.swap(true, Ordering::SeqCst) {
        app.dialog()
            .message(format!(
                "Veraxi Studio could not start its backend sidecar.\n\n{err}"
            ))
            .title("Veraxi Studio — Startup Error")
            .kind(MessageDialogKind::Error)
            .blocking_show();
        app.exit(1);
    }
}

struct SidecarGuard {
    child: Option<CommandChild>,
    #[cfg(windows)]
    job_handle: Option<isize>,
}

impl SidecarGuard {
    fn terminate(&mut self) {
        if let Some(child) = self.child.take() {
            let _ = child.kill();
        }
        #[cfg(windows)]
        if let Some(handle) = self.job_handle.take() {
            unsafe {
                windows_sys::Win32::Foundation::CloseHandle(handle as _);
            }
        }
    }
}

impl Drop for SidecarGuard {
    fn drop(&mut self) {
        self.terminate();
    }
}

struct SidecarState(Mutex<Option<SidecarGuard>>);

#[cfg(windows)]
fn attach_kill_on_close_job(pid: u32) -> Option<isize> {
    use std::mem::{size_of, zeroed};
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{
        OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
    };

    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return None;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let ok = SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const _,
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        );
        if ok == 0 {
            CloseHandle(job);
            return None;
        }
        let proc_handle = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
        if proc_handle.is_null() {
            CloseHandle(job);
            return None;
        }
        let assigned = AssignProcessToJobObject(job, proc_handle);
        CloseHandle(proc_handle);
        if assigned == 0 {
            CloseHandle(job);
            return None;
        }
        Some(job as isize)
    }
}

#[tauri::command]
async fn get_api_base_url(
    app: tauri::AppHandle,
    state: State<'_, ApiState>,
) -> Result<String, String> {
    let api_state = state.inner().clone();
    let res = tauri::async_runtime::spawn_blocking(move || {
        api_state.wait_ready(Duration::from_secs(30))
    })
    .await
    .map_err(|e| format!("Sidecar wait task failed: {e}"))?;

    if let Err(ref err) = res {
        show_startup_error_once(&app, state.inner(), err);
    }
    res
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(ApiState::new())
        .manage(SidecarState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![get_api_base_url])
        .setup(|app| {
            let api_state = app.state::<ApiState>().inner().clone();
            if cfg!(debug_assertions) {
                if let Ok(dev_url) = std::env::var("VERAXI_DEV_API_URL") {
                    let trimmed = dev_url.trim().trim_end_matches('/').to_string();
                    if !trimmed.is_empty() {
                        api_state.set_result(Ok(trimmed));
                        return Ok(());
                    }
                }
            }

            let workspace_dir = app
                .path()
                .app_local_data_dir()
                .map(|p| p.join("workspace"))
                .unwrap_or_else(|_| std::env::temp_dir().join("VeraxiStudio").join("workspace"));
            let _ = std::fs::create_dir_all(&workspace_dir);

            let sidecar_cmd = app.shell().sidecar("veraxi-sidecar")?.args([
                "serve",
                "--port",
                "0",
                "--workspace",
                &workspace_dir.to_string_lossy(),
            ]);

            let (mut rx, child) = sidecar_cmd.spawn()?;
            let pid = child.pid();

            #[cfg(windows)]
            let job_handle = attach_kill_on_close_job(pid);

            if let Ok(mut state_guard) = app.state::<SidecarState>().0.lock() {
                *state_guard = Some(SidecarGuard {
                    child: Some(child),
                    #[cfg(windows)]
                    job_handle,
                });
            }

            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let mut sent = false;
                let mut stderr_tail: Vec<String> = Vec::new();
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line_bytes) => {
                            let line = String::from_utf8_lossy(&line_bytes);
                            if !sent {
                                if let Some(rest) = line.trim().strip_prefix("VERAXI_API_READY ") {
                                    api_state.set_result(Ok(rest.trim().to_string()));
                                    sent = true;
                                }
                            }
                        }
                        CommandEvent::Stderr(err_bytes) => {
                            let err = String::from_utf8_lossy(&err_bytes);
                            eprintln!("[veraxi-sidecar] {err}");
                            let trimmed = err.trim();
                            if !trimmed.is_empty() {
                                stderr_tail.push(trimmed.to_string());
                                if stderr_tail.len() > 12 {
                                    stderr_tail.remove(0);
                                }
                            }
                        }
                        CommandEvent::Error(err) => {
                            if !sent {
                                let msg = format!("Sidecar error: {err}");
                                api_state.set_result(Err(msg.clone()));
                                show_startup_error_once(&app_handle, &api_state, &msg);
                                sent = true;
                            }
                        }
                        CommandEvent::Terminated(payload) => {
                            if !sent {
                                let detail = if stderr_tail.is_empty() {
                                    String::new()
                                } else {
                                    format!("\n\nSidecar output:\n{}", stderr_tail.join("\n"))
                                };
                                let msg = format!(
                                    "Sidecar exited prematurely (code: {:?}){detail}",
                                    payload.code
                                );
                                api_state.set_result(Err(msg.clone()));
                                show_startup_error_once(&app_handle, &api_state, &msg);
                                sent = true;
                            }
                            break;
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Veraxi Studio Tauri application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            if let Ok(mut guard) = app_handle.state::<SidecarState>().0.lock() {
                if let Some(mut sidecar) = guard.take() {
                    sidecar.terminate();
                }
            }
        }
    });
}
