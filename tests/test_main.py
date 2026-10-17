"""진입점 main.py가 불러와지는지 (합치는 과정에서 없는 모듈을 부르게 되는 일을 막는다)."""
import importlib


def test_main_module_imports():
    main = importlib.import_module("main")
    assert callable(main.main)
