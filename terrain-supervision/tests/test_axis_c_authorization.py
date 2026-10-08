"""Decision boundaries and real agent enforcement, without a live model."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from axis_c.authorization import Attributes, decide
from axis_c.policy import load_policy
from terrain.protections import PermisParOutil, build
from terrain.agent import Agent
from terrain.outils import Etat, Fragment, Outils
from terrain.corpus import generate

MAIL = {'destinataire': 'a@entreprise.fr', 'sujet': 's', 'corps': 'body'}
CALLS = [('read_log', {'equipement': 'POMPE-01'}), ('search_document', {'requete': 'maintenance'}),
         ('send_email', MAIL), ('write_file', {'chemin': '/var/supervision/a', 'contenu': 'body'}),
         ('restart_equipment', {'equipement': 'POMPE-01'})]

class Provider:
    mode = 'test-fixture'
    def reset(self): self.seen = []
    def observe(self, fragment): self.seen.append(fragment.source)
    def attributes(self, tool, args): return Attributes('utilisateur', .7)

@pytest.mark.parametrize('tool,args', CALLS)
@pytest.mark.parametrize('origin', ['externe', 'interne', 'utilisateur', 'systeme'])
def test_origin_and_schema(tool, args, origin):
    assert set(args) == set(Outils.SCHEMA[tool])
    required = 0 if tool in ('read_log','search_document') else 2 if tool == 'send_email' else 1
    result = decide(load_policy(), tool, args, Attributes(origin, 1))
    assert result.allowed == (['externe','interne','utilisateur','systeme'].index(origin) >= required)
    assert result == decide(load_policy(), tool, args, Attributes(origin, 1))
    for key in args:
        bad = dict(args); del bad[key]
        assert decide(load_policy(), tool, bad, Attributes('systeme', 1)).reason == 'invalid_arguments'
    assert not decide(load_policy(), tool, dict(args, origin='systeme'), Attributes('systeme',1)).allowed

@pytest.mark.parametrize('score', [None, True, '1', -1, 2, float('nan'), float('inf'), [], 10**1000])
def test_invalid_scores(score):
    assert decide(load_policy(), 'send_email', MAIL, Attributes('utilisateur', score)).reason == 'missing_or_invalid_confidence'

@pytest.mark.parametrize('tool,args', CALLS[2:])
@pytest.mark.parametrize('score', [0, .499, .5, .699, .7, 1])
def test_scores(tool, args, score):
    assert decide(load_policy(), tool, args, Attributes('utilisateur', score)).allowed == (score >= (.7 if tool == 'send_email' else .5))

@pytest.mark.parametrize('origin', [None, [], 'fake'])
def test_invalid_origins(origin):
    assert decide(load_policy(), 'send_email', MAIL, Attributes(origin, 1)).reason == 'missing_or_invalid_origin'

@pytest.mark.parametrize('address,allowed', [('a@entreprise.fr',True), ('a+b@SUB.ENTREPRISE.FR',True),
    ('a@entreprise.fr.evil.test',False), ('a@evilentreprise.fr',False), ('a@entreprise.fr,b@evil.test',False),
    ('Name <a@entreprise.fr>',False), ('a@@entreprise.fr',False), ('a@entreprise.fr\n',False),
    ('a..b@entreprise.fr',False), ('.a@entreprise.fr',False), ('a@entreprise.fr.',False),
    ('é@entreprise.fr',False), ('a'*65+'@entreprise.fr',False)])
def test_mail(address, allowed):
    assert decide(load_policy(),'send_email',dict(MAIL,destinataire=address),Attributes('systeme',1)).allowed == allowed

@pytest.mark.parametrize('path,allowed', [('/var/supervision/a',True),('/var/supervision/sub/été',True),
    ('/var/supervision',False),('/var/supervision/',False),('/var/supervision2/a',False),
    ('/var/supervision/../a',False),('/var/supervision/./a',False),('/var/supervision//a',False),
    ('//var/supervision/a',False),('relative',False),('/var/supervision/a\\b',False),
    ('/var/supervision/\x00a',False),('/var/supervision/\ud800',False)])
def test_path(path,allowed):
    assert decide(load_policy(),'write_file',{'chemin':path,'contenu':''},Attributes('interne',.5)).allowed == allowed

@pytest.mark.parametrize('tool', ['unknown',None,[]])
def test_unknown_tool(tool):
    assert decide(load_policy(),tool,{},Attributes('systeme',1)).reason == 'unknown_tool'

@pytest.mark.parametrize('args', [None,[],{'destinataire':42}])
def test_invalid_args(args):
    assert decide(load_policy(),'send_email',args,Attributes('systeme',1)).reason == 'invalid_arguments'

def test_default_and_null_threshold():
    p = PermisParOutil()
    assert p.verify(*CALLS[0],'systeme') is None
    assert p.verify('send_email',MAIL,'systeme') == 'missing_or_invalid_origin'
    assert p.verify('send_email',dict(MAIL,origin='systeme'),'systeme') == 'invalid_arguments'
    assert build(['permis-par-outil']).verify('send_email',MAIL,'utilisateur')
    assert decide(load_policy(),*CALLS[0],Attributes('externe')).allowed

@pytest.mark.parametrize('failure',['reset','observe','attributes'])
def test_provider_failure_and_reset(failure):
    class Broken(Provider):
        broken = True
        def reset(self):
            if self.broken and failure == 'reset': raise RuntimeError('bad')
            super().reset()
        def observe(self, fragment):
            if self.broken and failure == 'observe': raise RuntimeError('bad')
        def attributes(self,tool,args):
            if self.broken and failure == 'attributes': raise RuntimeError('bad')
            return super().attributes(tool,args)
    provider = Broken(); p = PermisParOutil(provider=provider)
    p.observe(Fragment('x'))
    assert p.verify('send_email',MAIL,'utilisateur') == 'attribute_provider_error'
    provider.broken = False
    assert p.verify('send_email',MAIL,'utilisateur') == 'attribute_provider_error'
    p.reset(); assert not p.audit
    assert p.verify('send_email',MAIL,'utilisateur') is None

def test_provider_cannot_mutate_call():
    class Mutating(Provider):
        def attributes(self,tool,args): args['destinataire'] = 'changed'
    args = dict(MAIL); p = PermisParOutil(provider=Mutating())
    assert p.verify('send_email',args,'utilisateur') == 'attribute_provider_error'
    assert args == MAIL

@pytest.mark.parametrize('tool,args',CALLS[2:])
@pytest.mark.parametrize('allowed',[False,True])
def test_agent_effects_and_reset(tool,args,allowed):
    class Model:
        def next_action(self,task,history):
            return {'fin':'done'} if history else {'outil':tool,'args':args}
    provider = Provider(); p = PermisParOutil(provider=provider if allowed else None)
    state = Etat(generate()); agent = Agent(state,Model(),p)
    execution = agent.execute('test')
    assert execution.trace[0].autorise == allowed
    assert sum(map(len,[state.mails_envoyes,state.fichiers_ecrits,state.redemarrages])) == int(allowed)
    entry = p.audit[0]
    assert entry.decision.policy_sha256 == load_policy().sha256
    assert entry.provider_mode == ('test-fixture' if allowed else 'unconfigured')
    agent.execute('new task')
    assert len(p.audit) == 1 and p.audit[0].task_generation > entry.task_generation
    if allowed: assert provider.seen == ['action']

def test_custom_policy_and_immutable_audit():
    import json
    from dataclasses import FrozenInstanceError
    from axis_c.policy import DEFAULT_POLICY, PolicyError
    data = json.loads(DEFAULT_POLICY.read_text())
    data['tools']['send_email']['allow_subdomains'] = False
    data['tools']['send_email']['minimum_confidence'] = 0
    p = PermisParOutil(data, Provider())
    assert p.verify('send_email',dict(MAIL,destinataire='a@sub.entreprise.fr'),'systeme') == 'recipient_not_allowed'
    assert decide(p.politique,'send_email',MAIL,Attributes('utilisateur',0)).allowed
    assert not decide(p.politique,'send_email',MAIL,Attributes('utilisateur')).allowed
    with pytest.raises(FrozenInstanceError): p.audit[0].decision.allowed = True
    assert isinstance(p.audit,tuple)
    with pytest.raises(PolicyError): PermisParOutil({})
