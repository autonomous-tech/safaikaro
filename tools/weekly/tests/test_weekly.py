"""Smallest checks that fail if the logic breaks: week windows, area extractor, lint on a bad page, renderer on a fixture.
Run: python3 -m pytest tools/weekly/tests -q   (or: python3 tools/weekly/tests/test_weekly.py)
"""
import datetime as dt, json, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common, collect, lint, send  # noqa: E402


def test_windows_monday_run():
    w = common.windows(dt.date(2026, 9, 7))  # a Monday
    assert w["this_week"] == (dt.date(2026, 8, 31), dt.date(2026, 9, 6))
    assert w["last_week"] == (dt.date(2026, 8, 24), dt.date(2026, 8, 30))
    assert w["last_28d"][1] == dt.date(2026, 9, 6) and (w["last_28d"][1] - w["last_28d"][0]).days == 27
    assert w["prior_28d"][1] == w["last_28d"][0] - dt.timedelta(days=1)


def test_windows_midweek_run_uses_last_complete_week():
    w = common.windows(dt.date(2026, 9, 9))  # Wednesday
    assert w["this_week"] == (dt.date(2026, 8, 31), dt.date(2026, 9, 6))


def test_prefill_area_three_live_shapes():
    assert collect.prefill_area("Hi SafaiKaro, I need pest control in Gulshan-e-Iqbal Karachi (ref: home/sticky)") == "gulshan-e-iqbal"
    assert collect.prefill_area("Hi SafaiKaro, I need rat and rodent control in Karachi") is None
    assert collect.prefill_area("Fumigation in Karachi.\nBuilding type: Office\nArea: Korangi Industrial Area & Zone 5\nPlease tell me") == "korangi-industrial-area"
    assert collect.prefill_area("") is None


def test_lint_catches_each_banned_condition():
    bad = ('<html><head><title>x</title><script>posthog.init(</script><script src="/prices.js"></script></head><body>'
           '<p>We are PPCP-certified — call now. Fumigation from Rs 99,999.</p><a href="/no-such-page">x</a>'
           '<script type="application/ld+json">{"@type":"FAQPage","mainEntity":[{"name":"Question not on page?"}]}</script></body></html>')
    out = lint.lint_html(common.ROOT / "zz-lint-fixture.html", bad, True, {7000}, ["PPCP"], {"https://safaikaro.pk/"})
    kinds = " ".join(out)
    for needle in ("banned phrase", "em-dash", "Rs 99,999", "broken internal link", "FAQ schema question", "not in sitemap"):
        assert needle in kinds, (needle, out)


def test_lint_passes_clean_page():
    good = ('<html><head><title>x</title><script>posthog.init(</script><script src="/prices.js"></script></head><body>'
            '<p>Cockroach fumigation from Rs 7,000, 90-day guarantee.</p><a href="/">home</a></body></html>')
    out = lint.lint_html(common.ROOT / "index.html", good, False, {7000}, ["PPCP"], {"https://safaikaro.pk/"})
    assert out == [], out


def test_pill_direction():
    assert "+12.0%" in send.pill(12.0)
    assert send.C["sage800"] in send.pill(12.0)
    assert send.C["red700"] in send.pill(-12.0)
    assert send.C["sage800"] in send.pill(-0.5, "", invert=True)
    assert "n/a" in send.pill(None)


def test_render_minimal_fixture():
    D = {"week": "2026-W36", "windows": {"this_week": ["2026-08-31", "2026-09-06"]}, "generated_at": "now", "errors": {},
         "posthog": {"funnel": {"this_week": {"total": {"lead_persons": 3, "visitors": 10, "lead_rate": 0.3}}}, "funnel_deltas": {}, "data_quality": {"sample_warning": True}},
         "gsc": {}, "ahrefs": {}, "health": {}, "cro": {}}
    html = send.render(D, {"narrative": "Quiet week."}, {"pr_url": "https://github.com/x/y/pull/7", "shipped": [{"type": "blog", "page": "/blog/a", "reason": "r", "critic": "passed"}]})
    assert "Quiet week." in html and "PR #7" in html and "Review and approve PR" in html and "/blog/a" in html


def test_price_gate_checks_added_copy_and_all_audits_legacy():
    path = common.ROOT / "index.html"
    text = '<p>Legacy machine price Rs 99,999.</p><p>SafaiKaro from Rs 7,000.</p>'
    kwargs = dict(path=path, text=text, is_new=False, prices={7000}, banned=[], sitemap=set())
    with patch.object(lint, "added_lines", return_value='<p>SafaiKaro from Rs 7,000.</p>'):
        assert lint.lint_html(**kwargs) == []
    with patch.object(lint, "added_lines", return_value='<p>SafaiKaro from Rs 99,998.</p>'):
        assert any('Rs 99,998' in x for x in lint.lint_html(**kwargs))
    # Whole-site audits retain legacy findings regardless of diff scope.
    assert any('Rs 99,999' in x for x in lint.lint_html(**kwargs, base=None))
    kwargs['is_new'] = True
    assert any('Rs 99,999' in x for x in lint.lint_html(**kwargs))


def test_nested_index_sitemap_route_is_exact():
    kwargs = dict(path=common.ROOT / "blog/index.html", text='<p>Blog</p>', is_new=False,
                  prices=set(), banned=[], base=None)
    assert lint.lint_html(**kwargs, sitemap={'https://safaikaro.pk/blog/'}) == []
    assert any('not in sitemap' in x for x in lint.lint_html(**kwargs, sitemap={'https://safaikaro.pk/blog'}))
    # Do not strip a literal index suffix from an ordinary page filename.
    kwargs['path'] = common.ROOT / 'price-index.html'
    assert lint.lint_html(**kwargs, sitemap={'https://safaikaro.pk/price-index'}) == []


def test_gate_includes_staged_html_from_base_diff():
    def fake_git(*args):
        return 'index.html' if args == ('diff', '--name-only', 'origin/main') else ''
    with patch.object(lint, 'git', side_effect=fake_git), patch.object(sys, 'argv', ['lint.py']), \
         patch.object(lint, 'lint_html', return_value=[]) as checker, \
         patch.object(lint, 'lint_ledgers', return_value=[]), \
         patch.object(lint.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='')):
        assert lint.main() == 0
        assert checker.call_count == 1
        assert checker.call_args.args[0] == common.ROOT / 'index.html'


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
