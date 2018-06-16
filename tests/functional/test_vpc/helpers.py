import nixops.util
import tempfile

def create_exprs_dir():
    return nixops.util.SelfDeletingDir(tempfile.mkdtemp("nixos-tests"))

def compose_expressions(configurations):
    exprs_dir = create_exprs_dir()

    extra_exprs = list(map(lambda x: generate_config(exprs_dir, x), configurations))

    nix_exprs = [base_spec] + extra_exprs
    return nix_exprs

def generate_config(exprs_dir, config):
    basename, expr = config
    expr_path = "{0}/{1}".format(exprs_dir, basename)
    with open(expr_path, "w") as cfg:
        cfg.write(expr)
    return expr_path
