"""Transactional new-sensor journal; existing provider history stays authoritative."""
import json
import sqlite3
from contextlib import contextmanager
from services.observations.contract import canonical

DDL = '''
CREATE TABLE IF NOT EXISTS raw_events (
 id TEXT PRIMARY KEY, received_at TEXT NOT NULL, topic TEXT NOT NULL,
 raw_sha256 TEXT NOT NULL, raw_base64 TEXT NOT NULL, decision TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations (
 id TEXT PRIMARY KEY, sequence BIGINT NOT NULL UNIQUE, raw_id TEXT REFERENCES raw_events(id), sensor_id TEXT NOT NULL,
 observed_at TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS observations_sensor_time ON observations(sensor_id, observed_at);
CREATE TABLE IF NOT EXISTS states (sensor_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata (id TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
'''


class Store:
    def __init__(self, connection, postgres=False):
        self.connection=connection;self.postgres=postgres

    @classmethod
    def sqlite(cls,path=':memory:'):
        connection=sqlite3.connect(path)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript(DDL)
        return cls(connection)

    @classmethod
    def postgres(cls,dsn):
        import psycopg2
        # Provisioning is deliberately separate; runtime has no CREATE privilege.
        return cls(psycopg2.connect(dsn,connect_timeout=5,options='-c search_path=earthship_observations,pg_catalog'),True)

    def execute(self,sql,args=()):
        cursor=self.connection.cursor()
        cursor.execute(sql.replace('?', '%s') if self.postgres else sql,args)
        return cursor

    @contextmanager
    def transaction(self):
        try:
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def state(self,sensor_id):
        row=self.execute('SELECT body FROM states WHERE sensor_id=?',(sensor_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def save_state(self,sensor_id,state):
        self.execute('INSERT INTO states(sensor_id,body) VALUES(?,?) ON CONFLICT(sensor_id) DO UPDATE SET body=excluded.body',
                     (sensor_id,canonical(state).decode()))

    def seen(self,event_id):
        row=self.execute('SELECT fingerprint FROM seen WHERE id=?',(event_id,)).fetchone()
        return None if row is None else row[0]

    def mark_seen(self,event_id,fingerprint):
        self.execute('INSERT INTO seen(id,fingerprint) VALUES(?,?)',(event_id,fingerprint))

    def observation(self,raw_id,point):
        from uuid import uuid4
        self.execute('INSERT INTO observations(id,sequence,raw_id,sensor_id,observed_at,body) VALUES(?,?,?,?,?,?)',
            (str(uuid4()),self.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM observations').fetchone()[0],raw_id,point['sensor_id'],point['observed_at'] or point['received_at'],canonical(point).decode()))

    def history(self,sensor_id=None,limit=2000):
        if type(limit) is not int or not 1<=limit<=50000:raise ValueError('bounded history query required')
        if sensor_id is None:
            rows=self.execute('SELECT body,sequence FROM observations ORDER BY observed_at DESC,sequence DESC LIMIT ?',(limit,)).fetchall()
        else:
            rows=self.execute('SELECT body,sequence FROM observations WHERE sensor_id=? ORDER BY observed_at DESC,sequence DESC LIMIT ?',(sensor_id,limit)).fetchall()
        return [{**json.loads(row[0]),'journal_sequence':row[1]} for row in rows]

    def count(self,table):
        if table not in ('raw_events','observations','states','seen'):raise ValueError('unknown table')
        return self.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def close(self):
        self.connection.close()
