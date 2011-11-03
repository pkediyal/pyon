#!/usr/bin/env python

"""Part of the container that manages ION processes etc."""

__author__ = 'Michael Meisinger'

from zope.interface import providedBy
from zope.interface import Interface, implements

from pyon.core.bootstrap import CFG
from pyon.net.endpoint import BinderListener, ProcessRPCServer, ProcessRPCClient
from pyon.service.service import add_service_by_name, get_service_by_name
from pyon.util.containers import DictModifier, DotDict, for_name
from pyon.util.log import log
from pyon.util.state_object import  LifecycleStateMixin

class ProcManager(LifecycleStateMixin):
    def on_init(self, container, *args, **kwargs):
        self.container = container

        # Define the callables that can be added to Container public API
        self.container_api = [self.spawn_process]

        # Add the public callables to Container
        for call in self.container_api:
            setattr(self.container, call.__name__, call)

        self.procs = {}

    def on_start(self, *args, **kwargs):
        log.debug("ProcManager: start")

    def on_stop(self, *args, **kwargs):
        log.debug("ProcManager: stop")

    def spawn_process(self, name=None, module=None, cls=None, config=None):
        """
        Spawn a process locally.
        """
        log.debug("In AppManager.spawn_process(name=%s, module=%s, config=%s)" % (name, module, config))

        # TODO: Process should get its own immutable copy of config, no matter what
        if config is None: config = DictModifier(CFG)

        log.debug("In AppManager.spawn_process: for_name(mod=%s, cls=%s)" % (module, cls))
        process_instance = for_name(module, cls)
        # TODO: Check that this is a proper instance (interface)

        # Inject dependencies
        process_instance.clients = DotDict()
        log.debug("In AppManager.spawn_process dependencies: %s" % process_instance.dependencies)
        for dependency in process_instance.dependencies:
            dependency_service = get_service_by_name(dependency)
            dependency_interface = list(providedBy(dependency_service))[0]

            # @TODO: start_client call instead?
            client = ProcessRPCClient(node=self.container.node, name=dependency, iface=dependency_interface, process=process_instance)
            process_instance.clients[dependency] = client

        # Init process
        process_instance.CFG = config
        process_instance.service_init()

        # Add to global dict
        # TODO: This needs to go into the process list
        add_service_by_name(name, process_instance)

        rsvc = ProcessRPCServer(node=self.container.node, name=name, service=process_instance, process=process_instance)

        # Start an ION process with the right kind of endpoint factory
        listener = BinderListener(self.container.node, name, rsvc, None, None)
        self.container.proc_sup.spawn((CFG.cc.proctype or 'green', None), listener=listener)

        # Wait for app to spawn
        log.debug("Waiting for server %s listener ready", name)
        listener.get_ready_event().get()
        log.debug("Server %s listener ready", name)
