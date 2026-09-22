Vagrant.configure("2") do |config|

  # Base Ubuntu box used by all virtual machines
  config.vm.box = "ubuntu/jammy64"

  # All Vms share the same Virtualbox host-only network 
  machines = {
    "proxy-dev"  => "192.168.56.4",
    "proxy-test" => "192.168.56.5",
    "proxy-prod" => "192.168.56.6"
  }

  # Create and configure eaach virtual machine
  machines.each do |hostname, ip|
    config.vm.define hostname do |machine|

      # Set the hostname
      machine.vm.hostname = hostname

      # Configure a static private IP
      machine.vm.network "private_network",
        ip: ip

      # Information
      machine.vm.provider "virtualbox" do |vb|
        vb.memory = 1024
        vb.cpus = 1
        vb.name = hostname
      end

    end
  end

end
