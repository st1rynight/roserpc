# roserpc

Discord Rich Presence for Roblox running under [Rosemary](https://github.com/microlift/rosemary).

While you play, Discord shows **Playing Roblox** with:

* the experience you're in, and its creator (or "In a private/reserved server")
* the experience's icon, and how long you've been playing it
* *Join server* and *See game page* buttons, for your friends (Discord hides them on your own profile)
* "In the menus" while Roblox is open but you aren't in a game

It's the same presence Bloxstrap gives Roblox on Windows. roserpc runs alongside Rosemary and
doesn't modify it. It's plain Python with no packages beyond the standard library.

## Requirements

* **A Discord desktop client.** The browser version can't receive Rich Presence, because it has no
  IPC socket. The official client, Flatpak, Snap and Vesktop all work.
* **Roblox already running under Rosemary.**
* **For the AppImage:** an x86_64 glibc Linux system with FUSE (`fusermount3` or `fusermount`).
  Python isn't needed; the AppImage brings its own.
* **For the source install:** Python 3.10 or newer, and git.

## Install the AppImage (quickest)

On x86_64 Arch, Debian/Ubuntu, Gentoo, NixOS and most other glibc distributions:

```sh
mkdir -p ~/.local/bin
curl -fL -o ~/.local/bin/roserpc https://github.com/st1rynight/roserpc/releases/latest/download/roserpc-x86_64.AppImage
chmod +x ~/.local/bin/roserpc
~/.local/bin/roserpc
```

AppImages need FUSE. If yours doesn't start and mentions FUSE, either install it, or run
`~/.local/bin/roserpc --appimage-extract-and-run` instead:

| Distribution | FUSE package |
|---|---|
| Arch | `sudo pacman -S --needed fuse3` |
| Debian / Ubuntu | `sudo apt install fuse3` |
| Gentoo | `sudo emerge --ask --noreplace sys-fs/fuse` |
| NixOS | set `programs.appimage.enable = true;` and `programs.appimage.binfmt = true;`, or run it with `appimage-run` |

The AppImage doesn't work on Alpine, because its bundled Python needs glibc, or on FreeBSD. Use
the source install there.

To start the AppImage automatically with systemd:

```sh
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/roserpc.service <<'EOF'
[Unit]
Description=Discord Rich Presence for Roblox under Rosemary
After=graphical-session.target

[Service]
ExecStart=%h/.local/bin/roserpc
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now roserpc
```

To update, download it again with the same `curl` command, then restart roserpc.

## Install from source

### 1. Install the packages

#### Arch Linux

```sh
sudo pacman -S --needed python git discord
```

#### Debian / Ubuntu

Use Debian 12+ or Ubuntu 22.04+. Older releases ship a Python older than 3.10.

```sh
sudo apt install python3 git
```

For Discord, download the `.deb` from <https://discord.com/download> and install it:

```sh
sudo apt install ./discord-*.deb
```

#### Gentoo

```sh
sudo emerge --ask --noreplace dev-lang/python dev-vcs/git net-im/discord
```

Discord isn't free software, so Portage may refuse to install it until you accept its licence:

```sh
echo "net-im/discord all-rights-reserved" | sudo tee -a /etc/portage/package.license
```

#### Alpine Linux

Use Alpine 3.16 or newer. Discord's official build needs glibc, so on Alpine (which uses musl)
install it through Flatpak:

```sh
doas apk add python3 git flatpak
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub com.discordapp.Discord
```

#### FreeBSD

```sh
sudo pkg install python3 git
```

FreeBSD has no native Discord client. You need something that provides Discord's IPC socket, for
example:

* the Linux client running under the Linux compatibility layer (roserpc also looks in
  `/compat/linux/tmp`), or
* [arRPC](https://github.com/OpenAsar/arrpc) together with Discord in a browser.

FreeBSD has no Linux-style `/proc`, so roserpc finds Roblox through `ps` instead. Because of that
it can't read Roblox's own Rosemary settings. If you start Roblox with a custom `ROSEMARY_PREFIX`,
either run roserpc with the same variable or pass `--log-dir`.

#### NixOS

Add this to `configuration.nix`, then run `sudo nixos-rebuild switch`:

```nix
nixpkgs.config.allowUnfree = true;   # Discord is unfree
environment.systemPackages = with pkgs; [ python3 git discord ];
```

### 2. Download roserpc

```sh
git clone https://github.com/st1rynight/roserpc ~/roserpc
```

The autostart files below assume roserpc is in `~/roserpc`. If you clone it somewhere else, change
the path in them.

### 3. Run it

```sh
~/roserpc/bin/roserpc
```

Leave it running, start Roblox through Rosemary as usual, and join a game. Stop it with Ctrl+C.
On NixOS without Python installed system-wide, use `nix-shell -p python3 --run ~/roserpc/bin/roserpc`.

### 4. Start it automatically (optional)

**systemd** (Arch, Debian/Ubuntu, Gentoo with systemd):

```sh
mkdir -p ~/.config/systemd/user
cp ~/roserpc/contrib/roserpc.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now roserpc
journalctl --user -u roserpc -f        # watch what it's doing
```

**NixOS:** add the module to `configuration.nix`, then `sudo nixos-rebuild switch`:

```nix
imports = [ /home/<you>/roserpc/contrib/roserpc.nix ];
```

With a flake-based config, copy `contrib/roserpc.nix` into your configuration and import it from
there, since pure evaluation can't read your home directory.

**Everything else** (Gentoo with OpenRC, Alpine, FreeBSD): start roserpc with your desktop session:

```sh
mkdir -p ~/.config/autostart
sed "s|@ROSERPC@|$HOME/roserpc|" ~/roserpc/contrib/roserpc.desktop > ~/.config/autostart/roserpc.desktop
```

### Updating

```sh
git -C ~/roserpc pull
```

Then restart roserpc, for example with `systemctl --user restart roserpc`.

## Options

| Option | Effect |
|---|---|
| `--show-account` | Small image is your avatar, with "Playing on DisplayName (@username)". |
| `--no-buttons` | Leave out the *Join server* and *See game page* buttons. |
| `--hide-menu` | Show nothing in the Roblox menus, only while in a game. |
| `--log-dir DIR` | Roblox's log directory, if it isn't found automatically. |
| `--client-id ID` | A different Discord application (also the `ROSERPC_CLIENT_ID` variable). |
| `-v` | Debug logging. |

To pass options to the service, edit `ExecStart` in `~/.config/systemd/user/roserpc.service`, or
`Exec` in the autostart file.

## How it works

1. **Finding Roblox.** Rosemary runs the player as `rosemary run .../RobloxPlayer`, so roserpc
   looks for a process with `RobloxPlayer` among its arguments. It reads `/proc` on Linux and uses
   `ps` elsewhere.
2. **Knowing what you're playing.** Roblox writes a log inside the Rosemary prefix, at
   `~/.local/share/rosemary/prefixes/default/root/Users/<you>/Library/Logs/Roblox`. roserpc
   follows the newest one, and reads joins, teleports, private and reserved servers, and leaving
   from its lines. It honours the settings Roblox was started with: `ROSEMARY_PREFIX`,
   `ROSEMARY_PREFIX_HOME=host` and `XDG_DATA_HOME`.
3. **Names and pictures.** Experience names, creators, icons and avatars come from Roblox's
   public web APIs, and are cached.
4. **Talking to Discord.** roserpc sends the activity over Discord's local IPC socket. Discord
   only displays about one update every 15 seconds and quietly drops the rest, so roserpc waits
   15 seconds between updates and sends the newest state each time.
5. **Statuses set by games.** Experiences that support Bloxstrap's `BloxstrapRPC` messages can set
   their own text, timers and images.

The default Discord application is Bloxstrap's public one, which Discord names "Roblox". To use
your own: create an application named *Roblox* at <https://discord.com/developers/applications>,
upload an art asset with the key `roblox`, and pass the application's ID with `--client-id`.

## Troubleshooting

* **Nothing shows on Discord.** In Discord, open Settings → Activity Privacy and turn on *Share
  your detected activities with others*.
* **"cannot reach Discord"**. The Discord desktop client isn't running, or its socket isn't
  visible. A sandboxed Discord has to expose `discord-ipc-0` to the host. Flatpak and Snap
  Discord do this by default.
* **Stuck on "In the menus".** Run with `-v`, and check that the `following ...` line names the log
  Roblox is writing now. If it doesn't, pass `--log-dir`.
* **A new game takes a few seconds to appear.** This is expected: Discord only accepts an update
  every 15 seconds.

## Development

```sh
cd ~/roserpc && python3 -m unittest discover -s tests -v
```

To build the AppImage into `build/roserpc-x86_64.AppImage`, you need `curl`, `python3` and
`squashfs-tools`:

```sh
tools/build-appimage.sh
nix shell nixpkgs#squashfsTools -c tools/build-appimage.sh   # if squashfs-tools isn't installed
```

See [CLAUDE.md](CLAUDE.md) for how the code is organised.
