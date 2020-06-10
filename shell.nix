(import (
  fetchTarball {
    url = https://github.com/edolstra/flake-compat/archive/f012cc5092f01fc67d5cd6f04999f964c3e05cbf.tar.gz;
    sha256 = "1n8q7v7alq802kl3b6zan6v27whi2ppbnlv8df6cz64vqf658ija"; }) {
      src = builtins.fetchGit ./.;
}).shellNix
