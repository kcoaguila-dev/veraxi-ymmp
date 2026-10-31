"""
Unit tests for Official Assets and Data Standardization Engine.
"""

from pathlib import Path
from PIL import Image

from veraxi_ymmp.official_assets import (
    OfficialSourceCitation,
    OfficialAssetRegistry,
    _coerce_citation,
    render_official_image_slide,
    render_official_data_slide,
)
from veraxi_ymmp.broll import render_from_manifest


def test_official_source_citation_formatting() -> None:
    cite = OfficialSourceCitation(
        source_name="The PHP Group",
        source_url="https://www.php.net",
        published_date="2026年3月",
        verification_badge="公式発表",
    )
    assert "The PHP Group" in cite.format_citation()
    assert "2026年3月" in cite.format_citation()


def test_coerce_citation_from_various_types() -> None:
    # String
    c1 = _coerce_citation("出典: W3Techs Survey")
    assert c1.source_name == "W3Techs Survey"

    # Dict
    c2 = _coerce_citation({"name": "NVD NIST", "date": "2024-06", "badge": "CVE公式"})
    assert c2.source_name == "NVD NIST"
    assert c2.published_date == "2024-06"
    assert c2.verification_badge == "CVE公式"

    # None fallback
    c3 = _coerce_citation(None)
    assert c3.source_name == "公式ドキュメント"


def test_official_asset_registry_procedural_generation(tmp_path: Path) -> None:
    php_path = tmp_path / "php.png"
    img = OfficialAssetRegistry.generate_php_brand_badge(php_path)
    assert php_path.is_file()
    assert img.size == (800, 450)

    cve_path = tmp_path / "cve.png"
    img_cve = OfficialAssetRegistry.generate_cve_shield_badge(out_path=cve_path)
    assert cve_path.is_file()
    assert img_cve.size == (800, 450)

    w3_path = tmp_path / "w3techs.png"
    img_w3 = OfficialAssetRegistry.generate_w3techs_stat_graphic(out_path=w3_path)
    assert w3_path.is_file()
    assert img_w3.size == (800, 450)

    arch_path = tmp_path / "arch.png"
    img_arch = OfficialAssetRegistry.generate_architecture_diagram(out_path=arch_path)
    assert arch_path.is_file()
    assert img_arch.size == (800, 450)


def test_official_asset_registry_resolve_preset() -> None:
    # Preset 'php' resolves to a real file
    res = OfficialAssetRegistry.resolve_asset("php")
    assert res.is_file()
    assert res.suffix == ".png"


def test_render_official_image_slide_landscape(tmp_path: Path) -> None:
    dest = tmp_path / "official_img_slide.png"
    out = render_official_image_slide(
        out_path=dest,
        title="PHP公式最新アーキテクチャ",
        image_path="php",
        source_citation="The PHP Group (php.net)",
        step_tag="公式発表",
        caption="Webの77%以上を支える基盤言語",
        theme_color="blue",
        is_vertical=False,
    )
    assert out.is_file()
    with Image.open(out) as im:
        assert im.size == (1920, 1080)


def test_render_official_image_slide_vertical(tmp_path: Path) -> None:
    dest = tmp_path / "official_img_vertical.png"
    out = render_official_image_slide(
        out_path=dest,
        title="PHP公式発表",
        image_path="php",
        source_citation="php.net",
        step_tag="検証",
        caption="最新PHP 8.4の性能強化",
        theme_color="emerald",
        is_vertical=True,
    )
    assert out.is_file()
    with Image.open(out) as im:
        assert im.size == (1080, 720)


def test_render_official_data_slide_landscape(tmp_path: Path) -> None:
    dest = tmp_path / "official_data_slide.png"
    out = render_official_data_slide(
        out_path=dest,
        title="Webシェアの実態調査",
        hero_metric="77.4%",
        metric_label="世界全Webサイトの稼働シェア",
        source_citation={"source_name": "W3Techs", "published_date": "2026年3月"},
        step_tag="公的調査",
        impact_tag="本質",
        impact_text="他言語を圧倒する事実上の標準基盤",
        theme_color="blue",
        is_vertical=False,
    )
    assert out.is_file()
    with Image.open(out) as im:
        assert im.size == (1920, 1080)


def test_render_from_manifest_with_official_types(tmp_path: Path) -> None:
    manifest = [
        {
            "type": "official_image",
            "filename": "slide_official_img.png",
            "title": "公式ブランド",
            "image": "php",
            "source": "The PHP Group",
            "step_tag": "検証 01",
            "caption": "PHP 8.4最新リリース",
            "theme_color": "blue",
        },
        {
            "type": "official_data",
            "filename": "slide_official_stat.png",
            "title": "公式セキュリティ評価",
            "hero_metric": "CVSS 9.8",
            "metric_label": "PHP CGI重大脆弱性の脅威度",
            "source": "NVD NIST Advisory",
            "step_tag": "検証 02",
            "impact_tag": "対策",
            "impact_text": "公式最新版への即時パッチで保護",
            "theme_color": "red",
        },
    ]

    out_dir = tmp_path / "broll"
    generated = render_from_manifest(manifest, out_dir)
    assert len(generated) == 2
    assert (out_dir / "slide_official_img.png").is_file()
    assert (out_dir / "slide_official_stat.png").is_file()
