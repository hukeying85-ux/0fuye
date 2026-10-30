"""Checks for charged bilayer salt and native GPU run safety."""
from pathlib import Path

import pytest
from cgmd.config import Config
from cgmd.engine import Gromacs
from cgmd.pipeline import Pipeline, PipelineError
from cgmd.salt import ensure_salt_pairs
from cgmd.topology import parse_molecules


def test_adds_salt_pairs_without_changing_charge_or_atom_count(tmp_path):
    gro = tmp_path / 'system.gro'
    top = tmp_path / 'insane.top'
    names = ['ALA'] + ['W'] * 1000 + ['NA+'] * 30
    lines = ['test', str(len(names))]
    for i, name in enumerate(names, 1):
        lines.append(f'{i:5d}{name:<5}{name:>5}{i:5d}{1.:8.3f}{2.:8.3f}{3.:8.3f}')
    gro.write_text('\n'.join(lines + [' 10.0 10.0 10.0']) + '\n')
    top.write_text('[ system ]\ntest\n[ molecules ]\nProtein 1\nW 1000\nNA+ 30\n')
    result = ensure_salt_pairs(str(gro), str(top), 0.15, seed=7)
    assert result == {'target_pairs': 11, 'added_pairs': 11, 'water': 978, 'sodium': 41, 'chloride': 11}
    assert dict(parse_molecules(str(top))) == {'Protein': 1, 'W': 978, 'NA': 41, 'CL': 11}
    rows = gro.read_text().splitlines()[2:-1]
    assert len(rows) == len(names)
    assert [x[5:10].strip() for x in rows] == ['ALA'] + ['W'] * 978 + ['NA'] * 41 + ['CL'] * 11
    assert [int(x[15:20]) for x in rows] == list(range(1, len(names) + 1))


def test_gpu_openmp_specifies_one_rank(tmp_path):
    cfg = Config(workdir=str(tmp_path), dry_run=True, gmx_binary='gmx', ntomp=4)
    engine = Gromacs(cfg, logger=lambda _: None)
    engine.mdrun('eq')
    command = engine.commands[-1]
    assert command[command.index('-ntmpi') + 1] == '1'
    assert '-pme' not in command


def test_incomplete_equilibration_does_not_start_production(tmp_path, monkeypatch):
    cfg = Config(workdir=str(tmp_path / 'work'), sequence='AAAA', gmx_binary='gmx')
    p = Pipeline(cfg, str(tmp_path / 'out'), logger=lambda _: None)
    monkeypatch.setattr('cgmd.pipeline.resolve_martini3_dir', lambda *a, **kw: str(tmp_path))
    monkeypatch.setattr('cgmd.pipeline.probe_environment', lambda *a: {})
    for method in ('stage_structure', 'stage_martinize', 'stage_insane', 'stage_topology', 'stage_index', 'stage_em'):
        monkeypatch.setattr(p, method, lambda *a: {})
    monkeypatch.setattr(p, 'stage_equilibration', lambda: {'completed': False})
    monkeypatch.setattr(p, 'stage_production', lambda: pytest.fail('production was started'))
    with pytest.raises(PipelineError, match='equilibration incomplete'):
        p.run()


def test_cgmd_text_is_ascii():
    root = Path(__file__).resolve().parents[1] / 'code' / 'cgmd'
    for path in root.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            path.read_bytes().decode('ascii')
