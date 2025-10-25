#!/usr/bin/env python3
"""
Hunt Pro - Professional Hunting Assistant
Entry Point Module
This is the main entry point for the Hunt Pro application.
It handles dependency checking, argument parsing, and application startup.
"""
import argparse
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Optional, List
def parse_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Hunt Pro - Professional Hunting Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m huntpro                    # Start with GUI
  python -m huntpro --check-deps      # Check dependencies only
  python -m huntpro --force           # Force start even with missing deps
  python -m huntpro --debug           # Start with debug logging
  python -m huntpro --log-dir ./logs  # Custom log directory
        """
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="Hunt Pro 2.0.0 - Touch-Optimized Field Edition"
    )
    parser.add_argument(
        "--check-deps", "-c",
        action="store_true",
        help="Check dependencies and exit"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force start application even if dependencies are missing"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        help="Custom directory for log files"
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in console mode (not implemented yet)"
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable performance profiling"
    )
    return parser.parse_args(argv)
def diagnose_pyside6() -> bool:
    """Diagnose PySide6 installation issues."""
    print("\nDiagnosing PySide6 installation...")
    try:
        import PySide6
        print(f"   OK PySide6 package found at: {PySide6.__file__}")
        try:
            from PySide6 import QtCore
            print(f"   OK QtCore version: {QtCore.__version__}")
        except ImportError as e:
            print(f"   ERROR QtCore import failed: {e}")
            return False
        try:
            from PySide6 import QtWidgets
            print("   OK QtWidgets imported successfully")
        except ImportError as e:
            print(f"   ERROR QtWidgets import failed: {e}")
            return False
        try:
            from PySide6 import QtGui
            print("   OK QtGui imported successfully")
        except ImportError as e:
            print(f"   ERROR QtGui import failed: {e}")
            return False
        return True
    except ImportError:
        print("   ERROR PySide6 package not found")
        print(f"\nInstallation suggestions:")
        print(f"   1. Verify installation: {sys.executable} -m pip show PySide6")
        print(f"   2. Reinstall: {sys.executable} -m pip uninstall PySide6 && {sys.executable} -m pip install PySide6")
        print(f"   3. Check permissions: make sure you can write to site-packages")
        print(f"   4. Try system install: sudo apt install python3-pyside6 (Ubuntu/Debian)")
        return False
def check_dependencies() -> bool:
    """Check if required dependencies are available."""
    # Package name mapping: display_name -> (import_name, description)
    required_packages = {
        'PySide6': ('PySide6', 'GUI framework'),
        'numpy': ('numpy', 'Mathematical calculations'),
    }
    optional_packages = {
        'PyYAML': ('yaml', 'Configuration files (PyYAML) - will use JSON if not available'),
        'pyserial': ('serial', 'GPS device communication (pyserial)'),
        'requests': ('requests', 'Online features'),
        'Pillow': ('PIL', 'Image processing (PIL)'),
        'matplotlib': ('matplotlib', 'Advanced charting'),
    }
    missing_required = []
    missing_optional = []
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print(f"Python path: {':'.join(sys.path[:3])}...\n")
    for display_name, (import_name, description) in required_packages.items():
        try:
            module = __import__(import_name)
            # For PySide6, also check if we can import core components
            if import_name == 'PySide6':
                from PySide6 import QtCore, QtWidgets, QtGui
                print(f"OK {display_name}: {description} (version: {getattr(module, '__version__', 'unknown')})")
            else:
                print(f"OK {display_name}: {description}")
        except ImportError as e:
            missing_required.append(f"{display_name} ({description})")
            print(f"ERROR {display_name}: {description} - MISSING")
            if display_name == 'PySide6':
                print(f"   Import error: {e}")
    for display_name, (import_name, description) in optional_packages.items():
        try:
            __import__(import_name)
            print(f"OK {display_name}: {description}")
        except ImportError:
            missing_optional.append(f"{display_name} ({description})")
            print(f"WARNING {display_name}: {description} - OPTIONAL")
    if missing_required:
        print(f"\nMissing required dependencies:")
        for package in missing_required:
            print(f"   - {package}")
        # Special PySide6 diagnostic
        if any('PySide6' in pkg for pkg in missing_required):
            if not diagnose_pyside6():
                return False
        # Special handling for PySide6 installation
        install_commands = []
        for package in missing_required:
            pkg_name = package.split()[0]
            if pkg_name == 'PySide6':
                install_commands.append('PySide6')
            else:
                install_commands.append(pkg_name.lower())
        print(f"\nTry installing with:")
        print(f"   pip install --user " + " ".join(install_commands))
        print(f"   or")
        print(f"   python3 -m pip install --user " + " ".join(install_commands))
        return False
    if missing_optional:
        print(f"\nMissing optional dependencies (some features may be unavailable):")
        for package in missing_optional:
            print(f"   - {package}")
    return True
def setup_environment():
    """Setup the application environment."""
    # Add current directory to Python path for module imports
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    # Set environment variables for better Qt experience
    os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
    # Create necessary directories
    home_dir = Path.home() / "HuntPro"
    home_dir.mkdir(exist_ok=True)
    (home_dir / "logs").mkdir(exist_ok=True)
    (home_dir / "data").mkdir(exist_ok=True)
    (home_dir / "exports").mkdir(exist_ok=True)
    (home_dir / "config").mkdir(exist_ok=True)
def run_with_profiling():
    """Run the application with performance profiling."""
    try:
        import cProfile
        import pstats
        from pathlib import Path
        # Create profiler
        profiler = cProfile.Profile()
        print("Starting Hunt Pro with performance profiling...")
        profiler.enable()
        # Run the main application
        from main import main
        exit_code = main()
        profiler.disable()
        # Save profiling results
        profile_dir = Path.home() / "HuntPro" / "profiles"
        profile_dir.mkdir(exist_ok=True)
        profile_file = profile_dir / f"huntpro_profile_{int(time.time())}.prof"
        profiler.dump_stats(str(profile_file))
        # Print summary
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        print(f"\nPerformance Profile Summary:")
        print(f"Profile saved to: {profile_file}")
        print("\nTop 10 functions by cumulative time:")
        stats.print_stats(10)
        return exit_code
    except ImportError:
        print("cProfile not available, running without profiling")
        from main import main
        return main()
def main():
    """Main entry point for Hunt Pro application."""
    try:
        # Parse command line arguments
        args = parse_arguments()
        # Print banner
        print("\n" + "="*60)
        print("Hunt Pro - Professional Hunting Assistant")
        print("   Version 2.0.0 - Touch-Optimized Field Edition")
        print("="*60 + "\n")
        # Setup environment
        setup_environment()
        # Check dependencies
        print("Checking dependencies...")
        deps_ok = check_dependencies()
        if args.check_deps:
            # Just check dependencies and exit
            if deps_ok:
                print("\nAll dependencies are satisfied!")
                return 0
            else:
                print("\nSome dependencies are missing!")
                return 1
        if not args.force and not deps_ok:
            print("\nCannot start application due to missing dependencies.")
            print("Use --force to attempt startup anyway, or install missing packages.")
            return 1
        if not deps_ok:
            print("\nStarting with missing dependencies (--force specified)")
            print("Some features may not work correctly.\n")
        # Set up logging level
        if args.debug:
            print("Debug logging enabled\n")
        # Start application
        if args.profile:
            return run_with_profiling()
        else:
            from main import main as run_main
            return run_main()
    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user")
        return 130
    except Exception as e:
        print(f"\nCritical error starting Hunt Pro:")
        print(f"   {type(e).__name__}: {e}")
        if args.debug if 'args' in locals() else False:
            print(f"\nDebug traceback:")
            traceback.print_exc()
        else:
            print(f"\nRun with --debug for detailed error information")
        return 1
if __name__ == "__main__":
    start_time = time.time()
    try:
        exit_code = main()
        runtime = time.time() - start_time
        print(f"\nHunt Pro ran for {runtime:.2f} seconds")
        sys.exit(exit_code)
    except SystemExit:
        runtime = time.time() - start_time
        print(f"\nHunt Pro ran for {runtime:.2f} seconds")
        raise
    except Exception as e:
        runtime = time.time() - start_time
        print(f"\nUnexpected error after {runtime:.2f} seconds: {e}")
        sys.exit(1)
