#!/usr/bin/env nix-shell
# !nix-shell ./shell.nix -i python3

from livereload import Server, shell

server = Server()

build_docs = shell("make html", cwd="doc")

print("Doing an initial build of the docs...")
build_docs()

server.watch("doc/*.rst", build_docs)
server.watch("doc/**/*.rst", build_docs)
server.serve(root="doc/_build/html")
