{ system ? builtins.currentSystem
, networkExprs
, checkConfigurationOptions ? true
, uuid
, deploymentName
, args
}:

with import <nixpkgs> { inherit system; };
with lib;


rec {

  networks =
    let
      getNetworkFromExpr = networkExpr:
        (call (import networkExpr)) // { _file = networkExpr; };

      exprToKey = key: { key = toString key; };

      networkExprClosure = builtins.genericClosure {
        startSet = map exprToKey networkExprs;
        operator = { key }: map exprToKey ((getNetworkFromExpr key).require or []);
      };
    in map ({ key }: getNetworkFromExpr key) networkExprClosure;

  call = x: if builtins.isFunction x then x args else x;

  network = zipAttrs networks;

  defaults = network.defaults or [];

  # Compute the definitions of the machines.
  nodes =
    listToAttrs (map (machineName:
      let
        # Get the configuration of this machine from each network
        # expression, attaching _file attributes so the NixOS module
        # system can give sensible error messages.
        modules =
          concatMap (n: optional (hasAttr machineName n)
            { imports = [(getAttr machineName n)]; inherit (n) _file; })
          networks;
      in
      { name = machineName;
        value = import <nixpkgs/nixos/lib/eval-config.nix> {
          modules =
            modules ++
            defaults ++
            [ deploymentInfoModule ] ++
            [ { key = "nixops-stuff";
                # Make NixOps's deployment.* options available.
                imports = [ ./options.nix ./resource.nix ];
                # Provide a default hostname and deployment target equal
                # to the attribute name of the machine in the model.
                networking.hostName = mkOverride 900 machineName;
                deployment.targetHost = mkOverride 900 machineName;
                environment.checkConfigurationOptions = mkOverride 900 checkConfigurationOptions;
              }
            ];
          extraArgs = { inherit nodes resources uuid deploymentName; name = machineName; };
        };
      }
    ) (attrNames (removeAttrs network [ "network" "defaults" "resources" "require" "_file" ])));

  # Compute the definitions of the non-machine resources.
  resourcesByType = zipAttrs (network.resources or []);

  deploymentInfoModule = {
    deployment = {
      name = deploymentName;
      arguments = args;
      inherit uuid;
    };
  };

  evalResources = mainModule: _resources:
    mapAttrs (name: defs:
      (builtins.removeAttrs (fixMergeModules
        ([ mainModule deploymentInfoModule ./resource.nix ] ++ defs)
        { inherit pkgs uuid name resources; nodes = info.machines; }
      ).config) ["_module"]) _resources;

  resources.sshKeyPairs = evalResources ./ssh-keypair.nix (zipAttrs resourcesByType.sshKeyPairs or []);

  # Amazon resources
  resources.snsTopics = evalResources ./sns-topic.nix (zipAttrs resourcesByType.snsTopics or []);
  resources.sqsQueues = evalResources ./sqs-queue.nix (zipAttrs resourcesByType.sqsQueues or []);
  resources.ec2KeyPairs = evalResources ./ec2-keypair.nix (zipAttrs resourcesByType.ec2KeyPairs or []);
  resources.s3Buckets = evalResources ./s3-bucket.nix (zipAttrs resourcesByType.s3Buckets or []);
  resources.iamRoles = evalResources ./iam-role.nix (zipAttrs resourcesByType.iamRoles or []);
  resources.ec2SecurityGroups = evalResources ./ec2-security-group.nix (zipAttrs resourcesByType.ec2SecurityGroups or []);
  resources.ec2PlacementGroups = evalResources ./ec2-placement-group.nix (zipAttrs resourcesByType.ec2PlacementGroups or []);
  resources.ebsVolumes = evalResources ./ebs-volume.nix (zipAttrs resourcesByType.ebsVolumes or []);
  resources.elasticIPs = evalResources ./elastic-ip.nix (zipAttrs resourcesByType.elasticIPs or []);
  resources.rdsDbInstances = evalResources ./ec2-rds-dbinstance.nix (zipAttrs resourcesByType.rdsDbInstances or []);
  resources.rdsDbSecurityGroups = evalResources ./ec2-rds-dbsecurity-group.nix (zipAttrs resourcesByType.rdsDbSecurityGroups or []);
  resources.route53RecordSets = evalResources ./route53-recordset.nix (zipAttrs resourcesByType.route53RecordSets or []);
  resources.elasticFileSystems = evalResources ./elastic-file-system.nix (zipAttrs resourcesByType.elasticFileSystems or []);
  resources.elasticFileSystemMountTargets = evalResources ./elastic-file-system-mount-target.nix (zipAttrs resourcesByType.elasticFileSystemMountTargets or []);
  resources.cloudwatchLogGroups = evalResources ./cloudwatch-log-group.nix (zipAttrs resourcesByType.cloudwatchLogGroups or []);
  resources.cloudwatchLogStreams = evalResources ./cloudwatch-log-stream.nix (zipAttrs resourcesByType.cloudwatchLogStreams or []);
  resources.cloudwatchMetricAlarms = evalResources ./cloudwatch-metric-alarm.nix (zipAttrs resourcesByType.cloudwatchMetricAlarms or []);
  resources.route53HostedZones = evalResources ./route53-hosted-zone.nix (zipAttrs resourcesByType.route53HostedZones or []);
  resources.route53HealthChecks = evalResources ./route53-health-check.nix (zipAttrs resourcesByType.route53HealthChecks or []);
  resources.vpc = evalResources ./vpc.nix (zipAttrs resourcesByType.vpc or []);
  resources.vpcSubnets = evalResources ./vpc-subnet.nix (zipAttrs resourcesByType.vpcSubnets or []);
  resources.vpcInternetGateways = evalResources ./vpc-internet-gateway.nix (zipAttrs resourcesByType.vpcInternetGateways or []);
  resources.vpcEgressOnlyInternetGateways = evalResources ./vpc-egress-only-internet-gateway.nix (zipAttrs resourcesByType.vpcEgressOnlyInternetGateways or []);
  resources.vpcDhcpOptions = evalResources ./vpc-dhcp-options.nix (zipAttrs resourcesByType.vpcDhcpOptions or []);
  resources.vpcNetworkAcls = evalResources ./vpc-network-acl.nix (zipAttrs resourcesByType.vpcNetworkAcls or []);
  resources.vpcNatGateways = evalResources ./vpc-nat-gateway.nix (zipAttrs resourcesByType.vpcNatGateways or []);
  resources.vpcNetworkInterfaces = evalResources ./vpc-network-interface.nix (zipAttrs resourcesByType.vpcNetworkInterfaces or []);
  resources.vpcNetworkInterfaceAttachments = evalResources ./vpc-network-interface-attachment.nix (zipAttrs resourcesByType.vpcNetworkInterfaceAttachments or []);
  resources.vpcRouteTables = evalResources ./vpc-route-table.nix (zipAttrs resourcesByType.vpcRouteTables or []);
  resources.vpcRouteTableAssociations = evalResources ./vpc-route-table-association.nix (zipAttrs resourcesByType.vpcRouteTableAssociations or []);
  resources.vpcRoutes = evalResources ./vpc-route.nix (zipAttrs resourcesByType.vpcRoutes or []);
  resources.vpcCustomerGateways = evalResources ./vpc-customer-gateway.nix (zipAttrs resourcesByType.vpcCustomerGateways or []);
  resources.vpcEndpoints = evalResources ./vpc-endpoint.nix (zipAttrs resourcesByType.vpcEndpoints or []);
  resources.awsVPNGateways = evalResources ./aws-vpn-gateway.nix (zipAttrs resourcesByType.awsVPNGateways or []);
  resources.awsVPNConnections = evalResources ./aws-vpn-connection.nix (zipAttrs resourcesByType.awsVPNConnections or []);
  resources.awsVPNConnectionRoutes = evalResources ./aws-vpn-connection-route.nix (zipAttrs resourcesByType.awsVPNConnectionRoutes or []);
  resources.output = evalResources ./output.nix (zipAttrs resourcesByType.output or []);
  resources.machines = mapAttrs (n: v: v.config) nodes;

  # Datadog resources
  resources.datadogMonitors = evalResources ./datadog-monitor.nix (zipAttrs resourcesByType.datadogMonitors or []);
  resources.datadogTimeboards = evalResources ./datadog-timeboard.nix (zipAttrs resourcesByType.datadogTimeboards or []);
  resources.datadogScreenboards = evalResources ./datadog-screenboard.nix (zipAttrs resourcesByType.datadogScreenboards or []);

  # hashicorp vault resources
  resources.vaultApprole = evalResources ./vault-approle.nix (zipAttrs resourcesByType.vaultApprole or []);

  # Azure resources
  resources.azureAvailabilitySets = evalAzureResources ./azure-availability-set.nix (zipAttrs resourcesByType.azureAvailabilitySets or []);
  resources.azureBlobContainers =
      evalResources ./azure-blob-container.nix
          (azure_default_containers // (zipAttrs resourcesByType.azureBlobContainers or []));
  resources.azureBlobs =
      evalResources ./azure-blob.nix
          (azure_default_blobs // (zipAttrs resourcesByType.azureBlobs or []));
  resources.azureDirectories = evalResources ./azure-directory.nix (zipAttrs resourcesByType.azureDirectories or []);
  resources.azureDNSRecordSets = evalResources ./azure-dns-record-set.nix (zipAttrs resourcesByType.azureDNSRecordSets or []);
  resources.azureDNSZones = evalAzureResources ./azure-dns-zone.nix (zipAttrs resourcesByType.azureDNSZones or []);
  resources.azureExpressRouteCircuits = evalAzureResources ./azure-express-route-circuit.nix (zipAttrs resourcesByType.azureExpressRouteCircuits or []);
  resources.azureFiles = evalResources ./azure-file.nix (zipAttrs resourcesByType.azureFiles or []);
  resources.azureGatewayConnections = evalAzureResources ./azure-gateway-connection.nix (zipAttrs resourcesByType.azureGatewayConnections or []);
  resources.azureLoadBalancers = evalAzureResources ./azure-load-balancer.nix (zipAttrs resourcesByType.azureLoadBalancers or []);
  resources.azureLocalNetworkGateways = evalAzureResources ./azure-local-network-gateway.nix (zipAttrs resourcesByType.azureLocalNetworkGateways or []);
  resources.azureQueues = evalResources ./azure-queue.nix (zipAttrs resourcesByType.azureQueues or []);
  resources.azureReservedIPAddresses = evalAzureResources ./azure-reserved-ip-address.nix (zipAttrs resourcesByType.azureReservedIPAddresses or []);
  resources.azureResourceGroups =
      evalAzureResourceGroups ./azure-resource-group.nix
          (azure_default_group // (zipAttrs resourcesByType.azureResourceGroups or []));
  resources.azureSecurityGroups = evalAzureResources ./azure-network-security-group.nix (zipAttrs resourcesByType.azureSecurityGroups or []);
  resources.azureShares = evalResources ./azure-share.nix (zipAttrs resourcesByType.azureShares or []);
  resources.azureStorages =
      evalAzureResources ./azure-storage.nix
          (azure_default_storages // (zipAttrs resourcesByType.azureStorages or []));
  resources.azureTables = evalResources ./azure-table.nix (zipAttrs resourcesByType.azureTables or []);
  resources.azureTrafficManagerProfiles = evalAzureResources ./azure-traffic-manager-profile.nix (zipAttrs resourcesByType.azureTrafficManagerProfiles or []);
  resources.azureVirtualNetworkGateways = evalAzureResources ./azure-virtual-network-gateway.nix (zipAttrs resourcesByType.azureVirtualNetworkGateways or []);
  resources.azureVirtualNetworks =
      evalAzureResources ./azure-virtual-network.nix
          (azure_default_networks // (zipAttrs resourcesByType.azureVirtualNetworks or []));

  # check if there are duplicate elements in a sorted list
  noDups = l:
    if length l > 1
    then
      if (head l) == (head (tail l))
      then throw "found resources with duplicate names: ${head l}"
      else noDups (tail l)
    else true;

  evalAzureResources = module: resources:
    let
      resourceGroup = r:
        if isAttrs r.resourceGroup
        then r.resourceGroup.name
        else r.resourceGroup;
      resourceNames = rs:
        sort lessThan
             (mapAttrsToList (n: v: toLower ("${resourceGroup v}/${v.name}")) rs);
      resources' = evalResources module resources;
    in assert (noDups (resourceNames resources')); resources';

  evalAzureResourceGroups = module: resources:
    let
      resourceNames = rs:
        sort lessThan
             (mapAttrsToList (n: v: toLower v.name) rs);
      resources' = evalResources module resources;
    in assert (noDups (resourceNames resources')); resources';


  azure_deployments = filterAttrs ( n: v: (scrubOptionValue v).config.deployment.targetEnv == "azure") nodes;

  azure_default_group = flip mapAttrs' azure_deployments (name: depl:
    let azure = (scrubOptionValue depl).config.deployment.azure; in (
      nameValuePair ("def-group") [ {
        inherit (azure) subscriptionId authority location identifierUri appId appKey;
      }]
    )
  );

  # "West US" -> "westus"
  normalize_location = l: builtins.replaceStrings [" "] [""] (toLower l);

  azure_default_networks = mapAttrs' (name: depl:
    let azure = (scrubOptionValue depl).config.deployment.azure; in (
      nameValuePair ("dn-${normalize_location azure.location}") [({ resources, ...}: {
        inherit (azure) subscriptionId authority location identifierUri appId appKey;
        resourceGroup = resources.azureResourceGroups.def-group;
        addressSpace = [ "10.1.0.0/16" ];
      })]
    )
  ) azure_deployments;

  azure_default_storages = mapAttrs' (name: depl:
    let azure = (scrubOptionValue depl).config.deployment.azure; in (
      nameValuePair ("def-storage-${normalize_location azure.location}") [({ resources, ...}: {
        inherit (azure) subscriptionId authority location identifireUri appId appKey;
        resourceGroup = resources.azureResourceGroups.def-group;
        name = "${builtins.substring 0 12 (builtins.replaceStrings ["-"] [""] uuid)}${normalize_location azure.location}";
      })]
    )
  ) azure_deployments;

  azure_default_containers = mapAttrs' (name: depl:
    let azure = (scrubOptionValue depl).config.deployment.azure; in (
      nameValuePair ("${azure.storage._name}-vhds") [({ resources, ...}: {
        inherit (azure) storage;
        name = "nixops-${uuid}-vhds";
      })]
    )
  ) azure_deployments;

  azure_default_blobs = mapAttrs' (name: depl:
    let azure = (scrubOptionValue depl).config.deployment.azure;
      images =
        let
          p = pkgs.path + "/nixos/modules/virtualisation/azure-images.nix";
          self = {
            "16.09" = "https://nixos.blob.core.windows.net/images/nixos-image-16.09.1694.019dcc3-x86_64-linux.vhd";
            latest = self."16.09";
          };
        in if pathExists p then import p else self;
    in (
      nameValuePair ("${azure.ephemeralDiskContainer._name}-image") [({ resources, ...}: {
        storage = azure.storage;
        container = azure.ephemeralDiskContainer;
        name = "nixops-${uuid}-unstable-image.vhd";
        blobType = "PageBlob";
        copyFromBlob = if args ? azure-image-url
                       then args.azure-image-url
                       else (images."${pkgs.lib.substring 0 5 pkgs.lib.nixpkgsVersion}" or images.latest);
      })]
    )
  ) azure_deployments;

  # Google Compute resources
  resources.gceDisks = evalResources ./gce-disk.nix (zipAttrs resourcesByType.gceDisks or []);
  resources.gceStaticIPs = evalResources ./gce-static-ip.nix (zipAttrs resourcesByType.gceStaticIPs or []);
  resources.gceNetworks = evalResources ./gce-network.nix (zipAttrs resourcesByType.gceNetworks or []);
  resources.gceHTTPHealthChecks = evalResources ./gce-http-health-check.nix (zipAttrs resourcesByType.gceHTTPHealthChecks or []);
  resources.gceTargetPools = evalResources ./gce-target-pool.nix (zipAttrs resourcesByType.gceTargetPools or []);
  resources.gceForwardingRules = evalResources ./gce-forwarding-rule.nix (zipAttrs resourcesByType.gceForwardingRules or []);
  resources.gseBuckets = evalResources ./gse-bucket.nix (zipAttrs resourcesByType.gseBuckets or []);
  resources.gceImages = evalResources ./gce-image.nix (gce_default_bootstrap_images // ( zipAttrs resourcesByType.gceImages  or []) );
  resources.gceRoutes = evalResources ./gce-routes.nix (zipAttrs resourcesByType.gceRoutes or []);

  gce_deployments = flip filterAttrs nodes
                      ( n: v: let dc = (scrubOptionValue v).config.deployment; in dc.targetEnv == "gce" );

  gce_default_bootstrap_images = flip mapAttrs' gce_deployments (name: depl:
    let
      gce = (scrubOptionValue depl).config.deployment.gce;

      images =
        let
          p = pkgs.path + "/nixos/modules/virtualisation/gce-images.nix";
          self = {
            "14.12" = "gs://nixos-cloud-images/nixos-14.12.471.1f09b77-x86_64-linux.raw.tar.gz";
            "15.09" = "gs://nixos-cloud-images/nixos-15.09.425.7870f20-x86_64-linux.raw.tar.gz";
            "16.03" = "gs://nixos-cloud-images/nixos-image-16.03.847.8688c17-x86_64-linux.raw.tar.gz";
            "17.03" = "gs://nixos-cloud-images/nixos-image-17.03.1082.4aab5c5798-x86_64-linux.raw.tar.gz";
            latest = self."17.03";
          };
        in if pathExists p then import p else self;
    in (
      nameValuePair ("bootstrap") [({ pkgs, ...}: {
        inherit (gce) project serviceAccount accessKey;
        sourceUri = images."${pkgs.lib.substring 0 5 pkgs.lib.nixpkgsVersion}" or images.latest;
      })]
    )
  );

  # Phase 1: evaluate only the deployment attributes.
  info =
    let
      network' = network;
      resources' = resources;
    in rec {

    machines =
      flip mapAttrs nodes (n: v': let v = scrubOptionValue v'; in
        { inherit (v.config.deployment) targetEnv targetPort targetHost encryptedLinksTo storeKeysOnMachine alwaysActivate owners keys hasFastConnection;
          nixosRelease = v.config.system.nixos.release or v.config.system.nixosRelease or (removeSuffix v.config.system.nixosVersionSuffix v.config.system.nixosVersion);
          azure = optionalAttrs (v.config.deployment.targetEnv == "azure")  v.config.deployment.azure;
          ec2 = optionalAttrs (v.config.deployment.targetEnv == "ec2") v.config.deployment.ec2;
          digitalOcean = optionalAttrs (v.config.deployment.targetEnv == "digitalOcean") v.config.deployment.digitalOcean;
          gce = optionalAttrs (v.config.deployment.targetEnv == "gce") v.config.deployment.gce;
          hetzner = optionalAttrs (v.config.deployment.targetEnv == "hetzner") v.config.deployment.hetzner;
          container = optionalAttrs (v.config.deployment.targetEnv == "container") v.config.deployment.container;
          route53 = v.config.deployment.route53;
          virtualbox =
            let cfg = v.config.deployment.virtualbox; in
            optionalAttrs (v.config.deployment.targetEnv == "virtualbox") (cfg
              // { disks = mapAttrs (n: v: v //
                { baseImage = if isDerivation v.baseImage then "drv" else toString v.baseImage; }) cfg.disks; });
          libvirtd = optionalAttrs (v.config.deployment.targetEnv == "libvirtd") v.config.deployment.libvirtd;
          publicIPv4 = v.config.networking.publicIPv4;
        }
      );

    network = fold (as: bs: as // bs) {} (network'.network or []);

    resources =
    let
      resource_referenced = list: check: recurse:
          any id (map (value: (check value) ||
                              ((isAttrs value) && (!(value ? _type) || recurse)
                                               && (resource_referenced (attrValues value) check false)))
                      list);
      azure_machines = mapAttrs (n: v: v.azure)
                                (filterAttrs ( n: v: v.targetEnv == "azure") machines);

      flatten_resources = resources: flatten ( map attrValues (attrValues resources) );

      resource_used = res_set: resource:
          resource_referenced
              ((flatten_resources res_set) ++ (attrValues azure_machines))
              (value: value == resource )
              true;

      resources_without_defaults = res_class: defaults: res_set:
        let
          missing = filter (res: !(resource_used (removeAttrs res_set [res_class])
                                                  res_set."${res_class}"."${res}"))
                           (attrNames defaults);
        in
        res_set // { "${res_class}" = ( removeAttrs res_set."${res_class}" missing ); };

    in  resources_without_defaults "azureResourceGroups" azure_default_group
       (resources_without_defaults "azureStorages" azure_default_storages
       (resources_without_defaults "azureBlobContainers" azure_default_containers
       (resources_without_defaults "azureBlobs" azure_default_blobs
       (resources_without_defaults "azureVirtualNetworks" azure_default_networks
       (removeAttrs resources' [ "machines" ])))));

  };

  # Phase 2: build complete machine configurations.
  machines = { names }:
    let nodes' = filterAttrs (n: v: elem n names) nodes; in
    runCommand "nixops-machines"
      { preferLocalBuild = true; }
      ''
        mkdir -p $out
        ${toString (attrValues (mapAttrs (n: v: ''
          ln -s ${v.config.system.build.toplevel} $out/${n}
        '') nodes'))}
      '';


  # Function needed to calculate the nixops arguments. This should work even when arguments
  # are not set yet, so we fake arguments to be able to evaluate the require attribute of
  # the nixops network expressions.

  dummyArgs = f: builtins.listToAttrs (map (a: lib.nameValuePair a false) (builtins.attrNames (builtins.functionArgs f)));

  getNixOpsExprs = l: lib.unique (lib.flatten (map getRequires l));

  getRequires = f:
    let
      nixopsExpr = import f;
      requires =
        if builtins.isFunction nixopsExpr then
          ((nixopsExpr (dummyArgs nixopsExpr)).require or [])
        else
          (nixopsExpr.require or []);
    in
      [ f ] ++ map getRequires requires;

  fileToArgs = f:
    let
      nixopsExpr = import f;
    in
      if builtins.isFunction nixopsExpr then
        map (a: { "${a}" = builtins.toString f; } ) (builtins.attrNames (builtins.functionArgs nixopsExpr))
      else [];

  getNixOpsArgs = fs: lib.zipAttrs (lib.unique (lib.concatMap fileToArgs (getNixOpsExprs fs)));

  nixopsArguments = getNixOpsArgs networkExprs;
}
