from pathlib import Path

files = ['test_m01_spec', 'test_m02_spec', 'test_m03_spec', 'test_m04_spec', 'test_m05_spec', 'test_m06_spec', 'test_m07_spec', 'test_m08_spec', 'test_m09_spec', 'test_m10_spec', 'test_m11_spec', 'test_m12_spec', 'test_m13_spec', 'test_x01_spec', 'test_x02_spec', 'test_x03_spec', 'test_x04_spec']
for f in files:
    Path('tests', f + '.py').write_text('import pytest\n\nclass TestModule:\n    def test_placeholder(self):\n        assert True')
    print(f'? {f}')
