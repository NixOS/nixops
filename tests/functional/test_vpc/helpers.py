import nixops.util
import tempfile

def compose_expressions(configurations):
    exprs_dir = create_exprs_dir()

    nix_exprs = list(map(lambda x: generate_config(exprs_dir, x), configurations))

    return nix_exprs

def create_exprs_dir():
    return nixops.util.SelfDeletingDir(tempfile.mkdtemp("nixos-tests"))

def generate_config(exprs_dir, config):
    basename, expr = config
    expr_path = "{0}/{1}".format(exprs_dir, basename)
    with open(expr_path, "w") as cfg:
        cfg.write(expr)
    return expr_path
