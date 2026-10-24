"""The wrapper may only publish a pin whose complete Tahoe CI passed."""
from pathlib import Path
import re


def test_release_requires_ci_for_exact_tahoe_pin():
    repo = Path(__file__).resolve().parents[1]
    text = (repo / '.github/workflows/release.yml').read_text()
    assert re.search(r'uses: lestercorderomurillo/macos-tahoe-liquid-kde/\.github/workflows/require-ci\.yml@[a-f0-9]{40}', text)
    assert 'sha: ${{ needs.source.outputs.commit }}' in text
    assert 'ref: ${{ needs.source.outputs.commit }}' in text
    assert 'repository: lestercorderomurillo/macos-tahoe-liquid-kde' in text
    assert 'needs: [source, ci]' in text.split('  publish:', 1)[1]
    assert 'actions: read' in text
