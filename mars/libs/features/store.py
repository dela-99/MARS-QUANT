from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib, json
import pandas as pd

@dataclass
class FeatureStoreManifest:
    dataset_id:str
    version:str
    path:str
    rows:int
    columns:list[str]
    fingerprint:str
    metadata:dict=field(default_factory=dict)

class FeatureStore:
    def __init__(self, root: str|Path): self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def _fingerprint(self, df:pd.DataFrame)->str:
        payload=pd.util.hash_pandas_object(df, index=True).values.tobytes()+repr(list(df.columns)).encode()
        return hashlib.sha256(payload).hexdigest()
    def write(self, dataset_id:str, version:str, df:pd.DataFrame, metadata:dict|None=None)->FeatureStoreManifest:
        folder=self.root/dataset_id/version; folder.mkdir(parents=True,exist_ok=True); path=folder/'features.parquet'; df.to_parquet(path)
        manifest=FeatureStoreManifest(dataset_id,version,str(path),len(df),list(df.columns),self._fingerprint(df),metadata or {})
        (folder/'manifest.json').write_text(json.dumps(asdict(manifest),indent=2,default=str),encoding='utf-8'); return manifest
    def read(self, dataset_id:str, version:str, columns:list[str]|None=None)->pd.DataFrame:
        return pd.read_parquet(self.root/dataset_id/version/'features.parquet', columns=columns)
    def manifest(self, dataset_id:str, version:str)->FeatureStoreManifest:
        data=json.loads((self.root/dataset_id/version/'manifest.json').read_text(encoding='utf-8')); return FeatureStoreManifest(**data)
    def query_duckdb(self, dataset_id:str, version:str, sql:str):
        try: import duckdb
        except ImportError as exc: raise RuntimeError('duckdb is required for query_duckdb') from exc
        path=str(self.root/dataset_id/version/'features.parquet').replace('\\','/')
        con=duckdb.connect(); return con.execute(sql.replace('{features}', f"read_parquet('{path}')")).df()
