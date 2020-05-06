#!/usr/bin/env nix-shell
#!nix-shell ./shell.nix -i python3

from livereload import Server, shell

server = Server()

server.watch("doc/*.rst", shell("make html", cwd="doc"))
server.watch("doc/**/*.rst", shell("make html", cwd="doc"))
server.serve(root="doc/_build/html")
