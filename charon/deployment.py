import sys
import os.path
import subprocess
import json
import uuid
import string
from xml.etree import ElementTree
import charon.backends


class Deployment:
    """Charon top-level deployment manager."""

    def __init__(self, state_file, create=False, nix_exprs=[]):
        self.state_file = state_file
        self.machines = { }
        
        self.expr_path = os.path.dirname(__file__) + "/../../../../share/nix/charon"
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.dirname(__file__) + "/../nix"

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
        self.machines = { }
        for n, v in state['machines'].iteritems():
            self.machines[n] = charon.backends.create_state(v['targetEnv'], n)
            self.machines[n].deserialise(v)
        
            
    def write_state(self):
        """Write the current deployment state to the state file in JSON format."""
        machines = {}
        for m in self.machines.itervalues():
            x = m.serialise()
            x["targetEnv"] = m.get_type()
            machines[m.name] = x
        state = {'networkExprs': self.nix_exprs,
                 'uuid': str(self.uuid),
                 'machines': machines}
        tmp = self.state_file + ".tmp"
        f = open(tmp, 'w')
        json.dump(state, f, indent=2)
        f.close()
        os.rename(tmp, self.state_file)


    def evaluate(self):
        """Evaluate the Nix expressions belonging to this deployment into a deployment model."""

        self.definitions = {}

        try:
            xml = subprocess.check_output(
                ["nix-instantiate", "-I", "charon=" + self.expr_path,
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
            defn = charon.backends.create_definition(m)
            self.definitions[defn.name] = defn


    def build_configs(self):
        """Build the machine configurations in the Nix store."""

        print >> sys.stderr, "building all machine configurations...";
        
        try:
            vms_path = subprocess.check_output(
                ["nix-build", "-I", "charon=" + self.expr_path, "--show-trace",
                 "<charon/eval-machine-info.nix>",
                 "--arg", "networkExprs", "[ " + string.join(self.nix_exprs) + " ]",
                 "-A", "machines"]).rstrip()
        except subprocess.CalledProcessError:
            raise Exception("unable to build all machine configurations")

        return vms_path
        

    def deploy(self):
        """Perform the deployment defined by the deployment model."""

        self.evaluate()

        # Create state objects for all defined machines.
        for m in self.definitions.itervalues():
            if m.name not in self.machines:
                print >> sys.stderr, "creating new machine ‘{0}’".format(m.name)
                self.machines[m.name] = charon.backends.create_state(m.get_type(), m.name)

        # Determine the set of active machines.  (We can't just delete
        # obsolete machines from ‘self.machines’ because they contain
        # important state that we don't want to forget about.)
        self.active = {}
        for m in self.machines.itervalues():
            if m.name in self.definitions:
                self.active[m.name] = m
            else:
                print >> sys.stderr, "machine ‘{0}’ is obsolete".format(m.name)
                # !!! If kill_obsolete is set, kill the machine.

        # Start or update the active machines.  !!! Should do this in parallel.
        for m in self.active.itervalues():
            m.create(self.definitions[m.name])

        self.write_state()
            
        # Build the machine configurations.
        vms_path = self.build_configs()

            

class NixEvalError(Exception):
    pass
