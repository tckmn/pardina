{ pkgs ? import <nixpkgs> {} }:
with pkgs; mkShell {
  nativeBuildInputs = [
    (python38.withPackages ( p: with p; [ aiohttp discordpy ] ))
  ];
}
