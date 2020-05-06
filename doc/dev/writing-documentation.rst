Writing Documentation
=====================

New NixOps documentation uses a standard configuration of Sphinx.
Older documentation is in Docbook, and should be ported to
reStructuredtext.

See Sphinx's primer on reStructuredText (reST):
https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html.

The NixOps repo has live-reloading support:

.. code-block:: shell

  nixops$ ./live-docs.py
  Serving on http://127.0.0.1:5500

Visit http://127.0.0.1:5500 in your browser. As you edit and save
``.rst`` files, your browser will automatically reload.

Before Committing
-----------------

Validate the source files for correctly written reST and spelling:

.. code-block:: shell

  nixops$ ./ci/lint-docs.sh

Fix any errors before committing.
