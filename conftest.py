"""pytest bootstrap — put the project root on sys.path so tests can
`import util`, `import gateway`, etc. without installing the package.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
