{
  description = "Macha - AI-Powered Autonomous System Administrator";

  inputs = {
    nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs }: {
    # NixOS module
    nixosModules.default = import ./module.nix;
    
    # Alternative explicit name
    nixosModules.ai-sysadmin = import ./module.nix;

    # For development
    devShells = nixpkgs.lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          requests
          psutil
          chromadb
        ]);
      in {
        default = pkgs.mkShell {
          packages = [ pythonEnv pkgs.git ];
          shellHook = ''
            echo "AI Sysadmin Development Environment"
            echo "Python packages: requests, psutil, chromadb"
          '';
        };
      }
    );

    # Formatter
    formatter = nixpkgs.lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (system:
      nixpkgs.legacyPackages.${system}.nixpkgs-fmt
    );
  };
}

