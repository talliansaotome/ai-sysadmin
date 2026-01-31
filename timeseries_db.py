#!/usr/bin/env python3
"""
TimescaleDB Integration - Store and query time-series metrics
"""

import os
import pwd
import psycopg2
from psycopg2.extras import execute_values
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json


class TimeSeriesDB:
    """Manage time-series metrics in TimescaleDB (PostgreSQL extension)"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = None,
        user: str = None,
        password: str = None
    ):
        """Initialize TimescaleDB connection"""
        # Auto-detect current user if not specified (e.g., macha-ai, alexander-ai)
        if user is None:
            try:
                user = pwd.getpwuid(os.getuid()).pw_name
            except:
                user = os.environ.get("USER", "postgres")
        
        # Default database to username if not specified
        if database is None:
            database = user
        
        # Force Unix socket for localhost to enable peer authentication
        if host == "localhost":
            host = ""
            
        self.conn_params = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password
        }
        self._ensure_schema()
    
    def _get_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.conn_params)
    
    def _ensure_schema(self):
        """Create tables and hypertables if they don't exist"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Enable TimescaleDB extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
                
                # System metrics table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        time TIMESTAMPTZ NOT NULL,
                        hostname TEXT NOT NULL,
                        metric_name TEXT NOT NULL,
                        value DOUBLE PRECISION,
                        unit TEXT,
                        metadata JSONB
                    );
                """)
                
                # Convert to hypertable if not already
                cur.execute("""
                    SELECT create_hypertable('system_metrics', 'time', 
                        if_not_exists => TRUE,
                        chunk_time_interval => INTERVAL '1 day');
                """)
                
                # Service status table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS service_status (
                        time TIMESTAMPTZ NOT NULL,
                        hostname TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        active_state TEXT,
                        metadata JSONB
                    );
                """)
                
                cur.execute("""
                    SELECT create_hypertable('service_status', 'time',
                        if_not_exists => TRUE,
                        chunk_time_interval => INTERVAL '1 day');
                """)
                
                # Log events table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS log_events (
                        time TIMESTAMPTZ NOT NULL,
                        hostname TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        message TEXT,
                        unit TEXT,
                        metadata JSONB
                    );
                """)
                
                cur.execute("""
                    SELECT create_hypertable('log_events', 'time',
                        if_not_exists => TRUE,
                        chunk_time_interval => INTERVAL '1 day');
                """)
                
                # Trigger events table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trigger_events (
                        time TIMESTAMPTZ NOT NULL,
                        hostname TEXT NOT NULL,
                        trigger_type TEXT NOT NULL,
                        trigger_reason TEXT,
                        metadata JSONB
                    );
                """)
                
                cur.execute("""
                    SELECT create_hypertable('trigger_events', 'time',
                        if_not_exists => TRUE,
                        chunk_time_interval => INTERVAL '1 day');
                """)
                
                # Create indexes for common queries
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_system_metrics_hostname_time 
                    ON system_metrics (hostname, time DESC);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_system_metrics_name 
                    ON system_metrics (metric_name, time DESC);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_service_status_hostname 
                    ON service_status (hostname, service_name, time DESC);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_log_events_severity 
                    ON log_events (hostname, severity, time DESC);
                """)
                
                conn.commit()
    
    def store_metrics(self, hostname: str, metrics: Dict[str, Any], timestamp: datetime = None):
        """Store system metrics"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        records = []
        for metric_name, metric_data in metrics.items():
            if isinstance(metric_data, dict):
                value = metric_data.get('value')
                unit = metric_data.get('unit', '')
                metadata = metric_data.get('metadata', {})
            else:
                value = float(metric_data) if metric_data is not None else None
                unit = ''
                metadata = {}
            
            if value is not None:
                records.append((
                    timestamp,
                    hostname,
                    metric_name,
                    value,
                    unit,
                    json.dumps(metadata)
                ))
        
        if records:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        """
                        INSERT INTO system_metrics 
                        (time, hostname, metric_name, value, unit, metadata)
                        VALUES %s
                        """,
                        records
                    )
                    conn.commit()
    
    def store_service_status(self, hostname: str, services: List[Dict[str, Any]], timestamp: datetime = None):
        """Store service status information"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        records = [
            (
                timestamp,
                hostname,
                svc.get('name', 'unknown'),
                svc.get('status', 'unknown'),
                svc.get('active_state', ''),
                json.dumps(svc.get('metadata', {}))
            )
            for svc in services
        ]
        
        if records:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        """
                        INSERT INTO service_status 
                        (time, hostname, service_name, status, active_state, metadata)
                        VALUES %s
                        """,
                        records
                    )
                    conn.commit()
    
    def store_log_event(self, hostname: str, severity: str, message: str, 
                       unit: str = "", metadata: Dict[str, Any] = None, 
                       timestamp: datetime = None):
        """Store a log event"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO log_events 
                    (time, hostname, severity, message, unit, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (timestamp, hostname, severity, message, unit, 
                     json.dumps(metadata or {}))
                )
                conn.commit()
    
    def store_trigger_event(self, hostname: str, trigger_type: str, 
                           trigger_reason: str, metadata: Dict[str, Any] = None,
                           timestamp: datetime = None):
        """Store a trigger event"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trigger_events 
                    (time, hostname, trigger_type, trigger_reason, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (timestamp, hostname, trigger_type, trigger_reason,
                     json.dumps(metadata or {}))
                )
                conn.commit()
    
    def query_metrics(self, hostname: str, metric_names: List[str] = None,
                     start_time: datetime = None, end_time: datetime = None,
                     interval: str = "5 minutes") -> List[Dict[str, Any]]:
        """Query metrics with optional time bucketing"""
        if start_time is None:
            start_time = datetime.utcnow() - timedelta(hours=1)
        if end_time is None:
            end_time = datetime.utcnow()
        
        where_clauses = ["hostname = %s", "time >= %s", "time <= %s"]
        params = [hostname, start_time, end_time]
        
        if metric_names:
            where_clauses.append("metric_name = ANY(%s)")
            params.append(metric_names)
        
        query = f"""
            SELECT 
                time_bucket(%s, time) AS bucket,
                metric_name,
                AVG(value) as avg_value,
                MAX(value) as max_value,
                MIN(value) as min_value,
                unit
            FROM system_metrics
            WHERE {' AND '.join(where_clauses)}
            GROUP BY bucket, metric_name, unit
            ORDER BY bucket DESC, metric_name
        """
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, [interval] + params)
                results = []
                for row in cur.fetchall():
                    results.append({
                        'time': row[0],
                        'metric_name': row[1],
                        'avg_value': row[2],
                        'max_value': row[3],
                        'min_value': row[4],
                        'unit': row[5]
                    })
                return results
    
    def query_latest_metrics(self, hostname: str, metric_names: List[str] = None) -> Dict[str, Any]:
        """Get the most recent value for each metric"""
        where_clauses = ["hostname = %s"]
        params = [hostname]
        
        if metric_names:
            where_clauses.append("metric_name = ANY(%s)")
            params.append(metric_names)
        
        query = f"""
            SELECT DISTINCT ON (metric_name)
                metric_name,
                value,
                unit,
                time
            FROM system_metrics
            WHERE {' AND '.join(where_clauses)}
            ORDER BY metric_name, time DESC
        """
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = {}
                for row in cur.fetchall():
                    results[row[0]] = {
                        'value': row[1],
                        'unit': row[2],
                        'time': row[3]
                    }
                return results
    
    def query_service_history(self, hostname: str, service_name: str,
                             hours: int = 24) -> List[Dict[str, Any]]:
        """Get service status history"""
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT time, status, active_state, metadata
                    FROM service_status
                    WHERE hostname = %s AND service_name = %s AND time >= %s
                    ORDER BY time DESC
                    """,
                    (hostname, service_name, start_time)
                )
                results = []
                for row in cur.fetchall():
                    results.append({
                        'time': row[0],
                        'status': row[1],
                        'active_state': row[2],
                        'metadata': row[3]
                    })
                return results
    
    def query_log_events(self, hostname: str, severity: str = None,
                        hours: int = 1) -> List[Dict[str, Any]]:
        """Query log events"""
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        where_clauses = ["hostname = %s", "time >= %s"]
        params = [hostname, start_time]
        
        if severity:
            where_clauses.append("severity = %s")
            params.append(severity)
        
        query = f"""
            SELECT time, severity, message, unit, metadata
            FROM log_events
            WHERE {' AND '.join(where_clauses)}
            ORDER BY time DESC
            LIMIT 1000
        """
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = []
                for row in cur.fetchall():
                    results.append({
                        'time': row[0],
                        'severity': row[1],
                        'message': row[2],
                        'unit': row[3],
                        'metadata': row[4]
                    })
                return results
    
    def get_metric_statistics(self, hostname: str, metric_name: str,
                             hours: int = 24) -> Dict[str, Any]:
        """Get statistical summary of a metric"""
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        AVG(value) as avg_value,
                        MAX(value) as max_value,
                        MIN(value) as min_value,
                        STDDEV(value) as stddev_value,
                        COUNT(*) as sample_count
                    FROM system_metrics
                    WHERE hostname = %s AND metric_name = %s AND time >= %s
                    """,
                    (hostname, metric_name, start_time)
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return {
                        'avg': row[0],
                        'max': row[1],
                        'min': row[2],
                        'stddev': row[3],
                        'samples': row[4],
                        'period_hours': hours
                    }
                return None
    
    def cleanup_old_data(self, retention_days: int = 30):
        """Remove data older than retention period"""
        cutoff_time = datetime.utcnow() - timedelta(days=retention_days)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # TimescaleDB uses chunks, so we can drop whole chunks efficiently
                cur.execute(
                    """
                    SELECT drop_chunks('system_metrics', older_than => %s);
                    """,
                    (cutoff_time,)
                )
                cur.execute(
                    """
                    SELECT drop_chunks('service_status', older_than => %s);
                    """,
                    (cutoff_time,)
                )
                cur.execute(
                    """
                    SELECT drop_chunks('log_events', older_than => %s);
                    """,
                    (cutoff_time,)
                )
                cur.execute(
                    """
                    SELECT drop_chunks('trigger_events', older_than => %s);
                    """,
                    (cutoff_time,)
                )
                conn.commit()


if __name__ == "__main__":
    # Test the database
    import socket
    
    db = TimeSeriesDB()
    hostname = socket.gethostname()
    
    # Store some test metrics
    db.store_metrics(hostname, {
        'cpu_percent': {'value': 45.5, 'unit': '%'},
        'memory_percent': {'value': 67.3, 'unit': '%'},
        'disk_usage_root': {'value': 82.1, 'unit': '%'}
    })
    
    # Query them back
    latest = db.query_latest_metrics(hostname)
    print("Latest metrics:", latest)
    
    # Get statistics
    stats = db.get_metric_statistics(hostname, 'cpu_percent', hours=24)
    print("CPU statistics:", stats)

