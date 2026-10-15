"""Official FalkorDB client lifecycle and schema readiness. No fallback store."""
import logging
import threading
import time
from falkordb import FalkorDB
from redis.exceptions import RedisError, ResponseError
from redis.retry import Retry
from redis.backoff import NoBackoff
from .config import Settings

log = logging.getLogger(__name__)

class GraphError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)

class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        self.graph = None
        self.ready = False
        self.lock = threading.Lock()

    def initialize(self):
        with self.lock:
            try:
                if self.client is None:
                    s = self.settings
                    self.client = FalkorDB(host=s.host, port=s.port, password=s.password,
                        ssl=s.ssl, socket_timeout=s.socket_timeout,
                        socket_connect_timeout=s.connect_timeout, max_connections=16,
                        retry=Retry(NoBackoff(), 0))
                    self.graph = self.client.select_graph(s.graph)
                self.graph.query('RETURN 1', timeout=self.settings.query_timeout_ms)
                rows = self.graph.ro_query('CALL db.constraints()').result_set
                found = [r for r in rows if r[:4] == ['UNIQUE','Entity',['id'],'NODE']]
                if not found:
                    try:
                        self.graph.create_node_unique_constraint('Entity', 'id')
                    except ResponseError as error:
                        if 'already exists' not in str(error).lower():
                            raise
                deadline = time.monotonic() + self.settings.socket_timeout
                while True:
                    rows = self.graph.ro_query('CALL db.constraints()').result_set
                    state = next((r[4] for r in rows if r[:4] == ['UNIQUE','Entity',['id'],'NODE']), None)
                    if state == 'OPERATIONAL':
                        self.ready = True
                        return
                    if state == 'FAILED' or time.monotonic() >= deadline:
                        raise GraphError(503, 'schema_unavailable', 'Graph identity constraint is not operational.')
                    time.sleep(.05)
            except RedisError as error:
                self.ready = False
                raise GraphError(503, 'database_unavailable', 'FalkorDB is unavailable or schema initialization failed.') from error

    def execute(self, cypher: str, params=None, *, read=False):
        if not self.ready:
            self.initialize()
        try:
            method = self.graph.ro_query if read else self.graph.query
            return method(cypher, params or {}, timeout=self.settings.query_timeout_ms).result_set
        except ResponseError as error:
            if 'unique' in str(error).lower() and 'constraint' in str(error).lower():
                raise GraphError(409, 'identity_conflict', 'This ID already identifies another entity.') from error
            log.exception('FalkorDB query failed')
            raise GraphError(503, 'query_failed', 'FalkorDB could not complete the operation.') from error
        except RedisError as error:
            self.ready = False
            raise GraphError(503, 'database_unavailable', 'FalkorDB is unavailable. Retry after restoring the database.') from error

    def close(self):
        if self.client is not None:
            self.client.close()
