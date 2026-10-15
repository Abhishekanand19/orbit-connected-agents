"""Read-only integration checks against the existing controlled sandbox."""
from backend.sandbox import probe
from backend.graph import sync, query
from backend.memory import recall

def test_order_is_real_and_working():
    assert probe('order') == {'order':'582','status':'SHIPPED'}

def test_graph_matches_probe():
    paths=sync()[1]
    result=probe('probe')['access']
    assert bool(paths) == (result=='granted')

def test_memory_survives_new_process():
    memory=recall()
    assert ['Order Lookup'] in memory['protected']
    assert memory['owner']
    assert any(row[1:]==['PASS','PASS'] for row in memory['verified'])

def test_approved_remediation_has_audit():
    assert query('MATCH (d:Decision)-[:APPROVED_BY]->(:Approval) WHERE d.status="verified" RETURN d.id')[1]
