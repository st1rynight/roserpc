# NixOS module: add `imports = [ /home/<you>/roserpc/contrib/roserpc.nix ];`
# to configuration.nix, then `sudo nixos-rebuild switch`.
{ pkgs, ... }:
{
  systemd.user.services.roserpc = {
    description = "Discord Rich Presence for Roblox under Rosemary";
    wantedBy = [ "default.target" ];
    after = [ "graphical-session.target" ];
    path = [ pkgs.python3 ];
    serviceConfig = {
      ExecStart = "%h/roserpc/bin/roserpc";
      Restart = "on-failure";
      RestartSec = 10;
    };
  };
}
