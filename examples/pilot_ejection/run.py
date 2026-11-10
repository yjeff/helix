"""Pilot Ejection 连续案例。"""
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

VA = 900.0
VE = 40.0
THE = 15.0 / 57.3
G = 32.2
RHO = 0.0023769
CD = 1.0
XS = 10.0
XM = 7.0

VX = VA - VE * math.sin(THE)
VY = VE * math.cos(THE)

INITIAL = {
    "X": 0.0,
    "Y": 0.0,
    "V": math.sqrt(VX * VX + VY * VY),
    "THETA": math.atan2(VY, VX),
    "LEFT_COCKPIT": 0.0,
}
CONSTANTS = {
    "VA": VA, "VE": VE, "THE": THE,
    "G": G, "RHO": RHO, "CD": CD, "XS": XS, "XM": XM,
}


def main() -> None:
    model = helix.Model.from_file(str(BASE / "model.helix"))
    result = model.initialize(
        initial=INITIAL, constants=CONSTANTS).run(end=4.0)

    final = result.continuous_final
    print("PILOT EJECTION")
    print("t_end:", round(result.now, 6))
    print("X:", round(final["X"], 6))
    print("Y:", round(final["Y"], 6))
    print("V:", round(final["V"], 6))
    print("THETA:", round(final["THETA"], 6))
    print("LEFT COCKPIT:", final["LEFT_COCKPIT"])

    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="PILOT EJECTION",
        track={
            "X": "VAR.X",
            "Y": "VAR.Y",
            "V": "VAR.V",
        },
        plot=["X", "Y"],
    )
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
