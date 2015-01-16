/*
This is an example RabbitMQ cluster application with PerfTest instances.

RabbitMQ is CPU-bound, so it makes sense to run it on n1-highcpu-* instances.
An instance of n1-highcpu-4 is capable of handling about 40k of "PerfTest -a"
messages per second.

About 5 PerfTest instances are required to load 3x n1-highcpu-4 cluster.
Admin interface is at http://cluster_ip:15672

Some deployment gotchas:
  rabbitmq has an autoclustering bug, which causes cluster to fail
  if all nodes are started at once. the code adds a startup delay
  for all nodes but the first one, but this is still unreliable.

  If node IP changes(eg due to start/stop/instance type change),
  it may fail to join the cluster without manual intervention.

  PerfTest nodes have 2 identical jobs because trying to use
  -x 2 -y 2 params to increase the number of threads in fact
  decreases the throughput(and causes 100% cpu utilization)
  probably due to scheduling issues. Separate processes also
  sometimes expose scheduling issues but not nearly as often
  and sometimes things settle by themselves after a warm-up
  period.

  there's no way to access load-balancer(cluster) ip in the
  deployment spec, so deployment has to happen in 2 steps.
  after the load-balancer is deployed, you have to manually
  replace amqp://rmq:123@146.148.2.203 with actual cluster url

*/

let
    pkgs = import <nixpkgs> {};

    # change this as necessary or wipe and use ENV vars
    credentials = {
        project = "logicblox-dev";
        serviceAccount = "572772620792-gecnc5v4ks9e6s13tociphd1p9ct6emr@developer.gserviceaccount.com";
        accessKey = "/home/freedom/nixos/phreedom/key.pem";
    };

    mkRabbitMQCluster = { prefix ? "rmq-", size, user ? "rmq", password, cookie, credentials, ipAddress ? null, region, extraConfig ? {}, extraGceConfig ? {} }:
    let
        cluster_node_names = map (id: "${prefix}${builtins.toString id}")
                                 ( pkgs.lib.range 0 (size - 1) );
        master_node_name = builtins.head cluster_node_names;
        mkClusterNode = { name, master }: {resources, ...}: {
            services.rabbitmq = {
                enable = true;
                listenAddress = "";
                plugins = [ "rabbitmq_management" "rabbitmq_management_visualiser" ];
                inherit cookie;
                config = ''
                    [
                        {rabbit, [
                            {default_user,        <<"${user}">>},
                            {default_pass,        <<"${password}">>},

                            {cluster_nodes, {[${ pkgs.lib.concatStringsSep "," (map (n: "'rabbit@${n}'")
                                                                                    #(builtins.filter (n: n!=name) cluster_node_names))
                                                                                    cluster_node_names)
                            }], disc}}
                        ]},
                        %%{kernel, [
                        %%    {inet_dist_listen_min, 10000},
                        %%    {inet_dist_listen_max, 10005}
                        %%]},
                        {rabbitmq_management, [{listener, [{port, 15672}]}]}
                        %%{rabbitmq_management_agent, [ {force_fine_statistics, false} ] }
                    ].
                '';
            };
            networking.firewall.enable = false; #allowedTCPPorts = [ 5672 4369 25672 15672];
            deployment.targetEnv = "gce";
            deployment.gce = credentials // {
                tags = ["rmq-node" "rmq-manager" ];
                network = resources.gceNetworks."${prefix}net";
            } // extraGceConfig;
        } // (pkgs.lib.optionalAttrs ( !master ) {
            systemd.services.wait-first-node = {
                description = "Let the first node start to work around rmq bug";
                wantedBy = [ "rabbitmq.service" ];
                before = [ "rabbitmq.service" ];
                script = ''
                    sleep 10
                '';
                serviceConfig.Type = "oneshot";
                serviceConfig.RemainAfterExit = true;
            };
         }) // extraConfig;

        cluster_nodes = pkgs.lib.fold pkgs.lib.mergeAttrs {}
                            (map (name: { "${name}" =  mkClusterNode { inherit name; master = (name == master_node_name);}; } )
                                 cluster_node_names );

    in {
        resources.gceHTTPHealthChecks."${prefix}hc" = credentials // {
            port = 15672;
        };

        resources.gceTargetPools."${prefix}tp" = {resources, nodes, ...}: credentials // {
            healthCheck = resources.gceHTTPHealthChecks."${prefix}hc";
            machines = map (name: nodes.${name}) cluster_node_names; # FIXME
            inherit region;
        };

        resources.gceForwardingRules."${prefix}cluster" = {resources, ...}: credentials // {
            protocol = "TCP";
            targetPool = resources.gceTargetPools."${prefix}tp";
            description = "RabbitMQ cluster";
            inherit ipAddress region;
        };

        resources.gceNetworks."${prefix}net" = credentials // {
            addressRange = "192.168.0.0/16";
            firewall = {
                allow-rmq = {
                    targetTags = ["rmq-node"];
                    allowed.tcp = [5672 4369 25672 "1000-65000" ];
                };
                allow-rmq-interface = {
                    targetTags = [ "rmq-manager" ];
                    allowed.tcp = [15672];
                };
            };
        };

    } // cluster_nodes;

    # this merges attrs up to 2 levels deep to handle resources
    # will fail if there are multiple defs of the same machine
    mergeNetworks = n1: n2:
      n1 // n2 // (pkgs.lib.optionalAttrs ((n1 ? resources) && (n2 ? resources))
          { resources = (pkgs.lib.mergeAttrsWithFunc pkgs.lib.mergeAttrs) n1.resources n2.resources; }
      );
    joinNetworks =  pkgs.lib.fold mergeNetworks {};



    perftest_node_count = 5;
    perftest_node_names = map (id: "perftest-${builtins.toString id}")
                              ( pkgs.lib.range 0 (perftest_node_count - 1) );
    perftest_node = {pkgs, resources, ...}: {
        networking.firewall.enable = false;
        environment.systemPackages = [ pkgs.rabbitmq-java-client ];
        deployment.targetEnv = "gce";

        systemd.services.pt1 = {
            path = [ pkgs.rabbitmq-java-client ];
            script = ''
                PerfTest -h amqp://rmq:123@146.148.2.203 -x 1 -y 1 -a
            '';
        };

        systemd.services.pt2 = {
            path = [ pkgs.rabbitmq-java-client ];
            script = ''
                PerfTest -h amqp://rmq:123@146.148.2.203 -x 1 -y 1 -a
            '';
        };

        deployment.gce = credentials // {
            tags = ["rmq-node" "rmq-manager" ];
            network = resources.gceNetworks.rmq-net;
            region = "europe-west1-b";
          #   instanceType = "f1-micro";
        };

    };

in


joinNetworks [
    (mkRabbitMQCluster {
        size = 3;
        password = "123";
        inherit credentials;
        region = "europe-west1";
        cookie = "jgnirughsdifgnsdkfgjnsdfj";
        extraGceConfig = {
          region = "europe-west1-b";
          instanceType = "n1-highcpu-4";
        };
    })

    # PerfTest instances
    ( pkgs.lib.fold pkgs.lib.mergeAttrs {}
          (map (name: { "${name}" =  perftest_node; } )
               perftest_node_names ) )

]
