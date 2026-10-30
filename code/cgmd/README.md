# CGMD-Engine: Martini 3 membrane pipeline

Builds a peptide, coarse grains it with martinize2, builds a POPE/POPG
membrane with INSANE, assembles a topology and index, then performs energy
minimization, equilibration, production and trajectory analysis. Large GROMACS
outputs must remain in the ignored run directory, not in git.

## Dependencies

Install Python packages `vermouth`, `insane`, `numpy`, `MDAnalysis` and
`matplotlib`. Use a CUDA-enabled GROMACS build for GPU production. Martini 3
parameters are not distributed on PyPI. The pipeline can shallow-clone
`https://github.com/marrink-lab/martini-forcefields.git` on demand and locates
`martini_forcefields/regular/v3.0.0/gmx_files`; alternatively set
`CGMD_MARTINI3_DIR` or use `--martini3-dir`. The force-field checkout is ignored
by git. `code/cgmd/setup_env.sh` is the optional WSL environment checker; the
mailbox pipeline runner uses native Windows Python and GROMACS instead.

## Usage

```sh
export PYTHONPATH="$PWD:$PWD/code/cgmd"
python -m cgmd.cli env-check
python -m cgmd.cli describe GIGKFLHSAKKFGKAFVGEIMNS
python -m cgmd.cli plan --sequence GIGKFLHSAKKFGKAFVGEIMNS
python -m cgmd.cli run --sequence GIGKFLHSAKKFGKAFVGEIMNS \
  --production-ns 100 --equilibration-ns 10 --gpu-id 0 \
  --workdir /path/to/local/run --output results/cgmd/example
```

`martinize2` uses the bundled `martini3001` force field and mappings, and runs
in the work directory. Single-letter secondary structure is expanded to the
residue count. The system topology uses flat copies of its force-field includes.
Martini 3 uses reaction-field electrostatics; dynamics use `-nb gpu -bonded gpu
-gpu_id N` without `-pme`. Energy minimization uses CPU bonded interactions:
GROMACS cannot offload bonded terms for the steep integrator.

INSANE's salt option accounts for neutralizing counterions. The builder adds
any missing NaCl pairs by replacing water beads, using four waters per Martini W
and nominal water density 55.5 M. This is an approximate initial concentration,
not a measurement of the equilibrated ionic concentration. Built-in structures are idealized, not experimental or
predicted conformations; simulation results depend on that starting model.

`stages.json` tracks progress. The small summary and SVGs are intended for
sharing; .tpr, .xtc, .edr, .gro and checkpoints stay local. A successful plan or
unit test does not prove a simulation actually ran. Do not interpret missing or
partial trajectory analysis as a measured insertion depth or pore formation.

## Tests

```sh
PYTHONPATH=.:code/cgmd MPLBACKEND=Agg python -m pytest tests -q
```
