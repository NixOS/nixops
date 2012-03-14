import os.path
import json
import uuid

class Deployment:
    """Charon top-level deployment manager"""

    def __init__(self, state_file, create=False, nix_exprs=[]):
        self.state_file = state_file

        if create:
            if os.path.exists(self.state_file):
                self.load_state()
            else:
                self.uuid = uuid.uuid1()
            self.nix_exprs = nix_exprs
        else:
            self.load_state()


    def load_state(self):
        f = open(self.state_file, 'r')
        state = json.load(f)
        self.nix_exprs = state['networkExprs']
        self.uuid = uuid.UUID(state['uuid'])
        
            
    def write_state(self):
        state = {'networkExprs': self.nix_exprs, 'uuid': str(self.uuid)}
        f = open(self.state_file, 'w')
        json.dump(state, f, indent=2)
