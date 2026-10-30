import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cg_pilot.pilot import (
    PilotError,
    command_plan,
    insane_counts,
    itp_atoms,
    mdp_text,
    normalize_gro,
    prepare,
    run,
    topol_text,
)


class PilotTests(unittest.TestCase):
    def test_atom_charge_mapping_and_insane_counts(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "pep.itp"
            path.write_text("[ atoms ]\n1 Q5 1 TYR BB 1 1.0\n2 Q5 2 ARG BB 2 -1\n3 Q5 2 ARG SC1 3 1\n[ bonds ]\n")
            beads, charge = itp_atoms(path)
            self.assertEqual((beads, charge), (["BB", "BB", "SC1"], 1))
            top = Path(root) / "insane.top"
            top.write_text("#include \"martini.itp\"\n[ molecules ]\nProtein 1\nW 100\nNA+ 1\nCL- 2\n")
            self.assertEqual(insane_counts(top), {"Protein": 1, "W": 100, "NA+": 1, "CL-": 2})
            self.assertRegex(topol_text(insane_counts(top)), r"(?m)^CL\s+2$")

    def test_gro_particle_count_and_ion_labels(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "system.gro"

            def atom(n, res, label):
                return f"{n % 100000:5d}{res:>5}{label:>5}{n % 100000:5d}{1.0:8.3f}{2.0:8.3f}{3.0:8.3f}"

            lines = [atom(1, "TYR", "BB")]
            lines.extend(atom(n + 2, "W", "W") for n in range(100))
            lines.append(atom(102, "NA+", "NA+"))
            lines += [atom(103, "CL-", "CL-"), atom(104, "CL-", "CL-")]
            path.write_text("test\n 104\n" + "\n".join(lines) + "\n 7.0 7.0 7.0\n")
            counts = {"W": 100, "NA+": 1, "CL-": 2}
            self.assertEqual(normalize_gro(path, ["BB"], counts), 104)
            normalized = path.read_text().splitlines()
            self.assertEqual(normalized[-4][5:15].strip(), "NA   NA")
            self.assertEqual(normalized[-3][5:15].strip(), "CL   CL")
            normalized[1] = "103"
            path.write_text("\n".join(normalized) + "\n")
            with self.assertRaisesRegex(PilotError, "particle count mismatch"):
                normalize_gro(path, ["BB"], counts)

    def test_plan_has_grompp_then_mdrun_and_is_not_an_abeta_run(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root)
            (work / "topol.top").write_text("placeholder\n")
            (work / "manifest.json").write_text(json.dumps({"status": "prepared_not_run"}))
            result = run(work, "gmx", 1, dry_run=True)
            self.assertEqual(result["status"], "dry_run_only")
            self.assertEqual(result["commands"], command_plan(work, "gmx", 1))
            self.assertEqual(len(result["commands"]), 8)
            self.assertEqual(result["commands"][0][1], "grompp")
            self.assertEqual(result["commands"][-1][1:4], ["mdrun", "-deffnm", "prod"])
            self.assertEqual(result["commands"][-1][-2:], ["-gpu_id", "1"])
            self.assertIn("nsteps = 5000", mdp_text("em", 5000, 42))
            self.assertIn("nsteps = 50000", mdp_text("npt", 50000, 42))
            self.assertIn("dt = 0.02", mdp_text("prod", 50000, 42))
            self.assertNotIn("pcoupl = C-rescale", mdp_text("nvt", 50000, 42))

    def test_failed_gmx_command_is_recorded_not_reported_as_completed(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root)
            (work / "topol.top").write_text("placeholder\n")
            (work / "manifest.json").write_text(json.dumps({"status": "prepared_not_run"}))
            fake_gmx = work / "fake-gmx"
            fake_gmx.touch()
            with patch("cg_pilot.pilot.invoke", side_effect=PilotError("synthetic grompp failure")):
                with self.assertRaisesRegex(PilotError, "synthetic"):
                    run(work, str(fake_gmx), 0, dry_run=False)
            result = json.loads((work / "manifest.json").read_text())
            self.assertEqual(result["status"], "failed_on_runner")
            self.assertEqual(result["stages"], [])
            self.assertNotIn("prod_gro_sha256", result)

    @unittest.skipUnless(os.getenv("MARTINI3_GMX_FILES"), "need pinned official forcefield + Python build dependencies")
    def test_official_forcefield_prepares_real_single_peptide(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root) / "run"
            data = prepare(work, Path(os.environ["MARTINI3_GMX_FILES"]), False, 0.1, 42)
            self.assertEqual(data["status"], "prepared_not_run")
            self.assertEqual(data["peptide_beads"], 18)
            self.assertEqual(data["system_beads"], sum(data["molecules"].values()) + 17)
            self.assertEqual(data["molecules"]["NA"] + 1, data["molecules"]["CL"])
            self.assertTrue((work / "system.gro").is_file())
            self.assertFalse((work / "prod.xtc").exists())
            self.assertEqual(json.loads((work / "manifest.json").read_text())["status"], "prepared_not_run")


if __name__ == "__main__":
    unittest.main()
