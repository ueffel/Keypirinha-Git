# Keypirinha Git

This is a package that extends the fast keystroke launcher keypirinha
(<http://keypirinha.com/>). It provides configurable commands to run on your git
repositories directly from keypirinha. For example: Opening the repository in
your favorite Git GUI Client or development enviroment.

## Usage

Configure your scan paths, to let the plugin find the git repositories on your
hard drive start using the plugin.

Available commands via default configuration include:

* Open repository path in Windows Explorer
* Open repository in Fork / GitExtensions / Sublime Merge (various GUI clients)
* Running automatic garbage collection on all found repositories (`git gc --auto`)
* more commands you can configure yourself

All item are prefixed with `Git:`

## Installation

### With [PackageControl](https://github.com/ueffel/Keypirinha-PackageControl)

Install Package "Keypirinha-Git"

### Manually

* Download the `Git.keypirinha-package` from the
  [releases](https://github.com/ueffel/Keypirinha-Git/releases/latest).
* Copy the file into `%APPDATA%\Keypirinha\InstalledPackages` (installed mode) or
  `<Keypirinha_Home>\portable\Profile\InstalledPackages` (portable mode)
