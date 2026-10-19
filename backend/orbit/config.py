from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os

class Settings(BaseModel):
    public_demo: bool = False
    allowed_hosts: list[str] = ['127.0.0.1','localhost','testserver']
    host: str = '127.0.0.1'
    port: int = Field(default=6380, ge=1, le=65535)
    graph: str = Field(default='orbit', pattern=r'^orbit(?:_[a-zA-Z0-9_-]+)?$', max_length=100)
    username: str | None = None
    password: str | None = None
    ssl: bool = False
    connect_timeout: float = Field(default=2, gt=0, le=30)
    socket_timeout: float = Field(default=5, gt=0, le=60)
    query_timeout_ms: int = Field(default=2000, ge=100, le=10000)
    allowed_origins: list[str] = ['http://127.0.0.1:5173', 'http://localhost:5173']

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[2] / '.env', encoding='utf-8-sig')
        names = {'public_demo':'ORBIT_PUBLIC_DEMO', 'host':'FALKORDB_HOST', 'port':'FALKORDB_PORT', 'graph':'FALKORDB_GRAPH',
                 'username':'FALKORDB_USERNAME', 'password':'FALKORDB_PASSWORD', 'ssl':'FALKORDB_SSL',
                 'connect_timeout':'FALKORDB_CONNECT_TIMEOUT', 'socket_timeout':'FALKORDB_SOCKET_TIMEOUT',
                 'query_timeout_ms':'FALKORDB_QUERY_TIMEOUT_MS'}
        values = {key:os.environ[env] for key,env in names.items() if os.environ.get(env)}
        if os.getenv('ORBIT_ALLOWED_ORIGINS'):
            values['allowed_origins'] = os.environ['ORBIT_ALLOWED_ORIGINS'].split(',')
        if os.getenv('ORBIT_ALLOWED_HOSTS'):
            values['allowed_hosts'] = [v.strip() for v in os.environ['ORBIT_ALLOWED_HOSTS'].split(',')]
        result = cls(**values)
        if result.public_demo and not result.graph.startswith('orbit_public_'):
            raise ValueError('Public demo requires a dedicated orbit_public_ registry graph.')
        return result
