from pathlib import Path
root=Path(r'C:\Users\RIDGE\MARS-QUANT')
base=root/'mars'/'libs'/'learning'
for d in ['base','datasets','labels','pipelines','preprocessing','feature_selection','models','models/xgboost','models/lightgbm','models/catboost','models/random_forest','models/logistic','models/svm','models/pytorch','models/lstm','models/transformer','training','evaluation','registry','serving','artifacts','validation']:
    (base/d).mkdir(parents=True, exist_ok=True)
    (base/d/'__init__.py').write_text('', encoding='utf-8')
print('dirs')
