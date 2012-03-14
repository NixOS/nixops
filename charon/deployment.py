import os.path
import subprocess
import json
import uuid
import string
from xml.etree import ElementTree


class Deployment:
    """Charon top-level deployment manager."""

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
        """Read the current deployment state from the state file."""
        f = open(self.state_file, 'r')
        state = json.load(f)
        self.nix_exprs = state['networkExprs']
        self.uuid = uuid.UUID(state['uuid'])
        
            
    def write_state(self):
        """Write the current deployment state to the state file in JSON format."""
        state = {'networkExprs': self.nix_exprs, 'uuid': str(self.uuid)}
        f = open(self.state_file, 'w')
        json.dump(state, f, indent=2)


    def evaluate(self):
        """Evaluate the Nix expressions belonging to this deployment into a deployment model."""

        expr_path = os.path.dirname(__file__) + "/../nix";
        
        try:
            xml = subprocess.check_output(
                ["nix-instantiate", "-I", "charon=" + expr_path,
                 "--eval-only", "--show-trace", "--xml", "--strict",
                 "<charon/eval-machine-info.nix>",
                 "--arg", "networkExprs", "[ " + string.join(self.nix_exprs) + " ]",
                 "-A", "info"])
        except subprocess.CalledProcessError:
            raise NixEvalError

        tree = ElementTree.fromstring(xml)

        # Extract global deployment attributes.
        info = tree.find("attrs/attr[@name='network']")
        assert info != None
        elem = info.find("attrs/attr[@name='name']/string")
        self.name = elem.get("value") if elem != None else ""

        # Extract machine information.
        machines = tree.find("attrs/attr[@name='machines']/attrs")

        for m in machines.findall("attr"):
            name = m.get("name")
            target_env = m.find("attrs/attr[@name='targetEnv']/string").get("value")
            assert name and target_env
            print "got machine", name, ", type is", target_env
            

class NixEvalError(Exception):
    pass
