import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from frontend.desktop_app import main

if __name__ == "__main__":
    main()
