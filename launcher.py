"""CIPA Crop & Coord GUI and optional local integrated-build smoke test."""
import sys


if __name__ == "__main__":
    if "--self-test-integrated" in sys.argv:
        from cipa_crop_coord.integrated_self_test import self_test_integrated
        raise SystemExit(self_test_integrated())
    from cipa_crop_coord.app import main
    raise SystemExit(main())
