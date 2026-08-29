from pathlib import Path
b=Path(r'C:\Users\RIDGE\OneDrive\Desktop\MARS-QUANT\mars\libs\learning')
for d in ['calibration','explainability','optimisation','ensembles','inference','persistence']:
    (b/d).mkdir(parents=True, exist_ok=True)
    (b/d/'__init__.py').write_text('', encoding='utf-8')
print('extra dirs')
