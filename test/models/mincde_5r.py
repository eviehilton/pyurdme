#!/usr/bin/env python
""" pyURDME model file for the MinCDE example. """

import matplotlib.pyplot as plt
import numpy
import os.path
import pyurdme
import dolfin
import numpy

class Membrane(dolfin.SubDomain):
    def inside(self,x,on_boundary):
        return on_boundary


class Cytosol(dolfin.SubDomain):
    def inside(self,x,on_boundary):
        return not on_boundary


class MeshSize(pyurdme.URDMEDataFunction):
    def __init__(self,mesh):
        pyurdme.URDMEDataFunction.__init__(self, name="MeshSize")
        self.mesh = mesh
        self.h = mesh.get_mesh_size()
    
    def map(self, x):
        ret = self.h[self.mesh.closest_vertex(x)]
        return ret

class MinCDE5R(pyurdme.URDMEModel):
    """ Model of MinCDE oscillations in E. Coli based on the model by Fange and Elf. """

    def __init__(self,model_name="mincde"):
        pyurdme.URDMEModel.__init__(self,model_name)

        # Species
        MinD_m     = pyurdme.Species(name="MinD_m",diffusion_constant=1e-14,dimension=2)
        MinD_c_atp = pyurdme.Species(name="MinD_c_atp",diffusion_constant=2.5e-12,dimension=3)
        MinD_c_adp = pyurdme.Species(name="MinD_c_adp",diffusion_constant=2.5e-12,dimension=3)
        MinD_e     = pyurdme.Species(name="MinD_e",diffusion_constant=2.5e-12,dimension=3)
        MinDE      = pyurdme.Species(name="MinDE",diffusion_constant=1e-14,dimension=2)
        
        self.add_species([MinD_m,MinD_c_atp,MinD_c_adp,MinD_e,MinDE])
        
        # Make sure that we have the correct path to the mesh file even if we are not executing from the basedir.
        basedir = os.path.dirname(os.path.abspath(__file__))
        self.mesh = pyurdme.URDMEMesh.read_dolfin_mesh(basedir+"/data/coli.xml")
        
        interior = dolfin.CellFunction("size_t",self.mesh)
        interior.set_all(1)
        boundary = dolfin.FacetFunction("size_t",self.mesh)
        boundary.set_all(0)
        
        # Mark the boundary points
        membrane = Membrane()
        membrane.mark(boundary,2)
        
        self.add_subdomain(interior)
        self.add_subdomain(boundary)
        
        # Average mesh size to feed into the propensity functions
        h = self.mesh.get_mesh_size()
        self.add_data_function(MeshSize(self.mesh))
        
        # Parameters
        NA = pyurdme.Parameter(name="NA",expression=6.022e23)
        sigma_d  = pyurdme.Parameter(name="sigma_d",expression=1.25e-8)
        sigma_dD = pyurdme.Parameter(name="sigma_dD",expression="9.0e6/(1000.0*NA)")
        sigma_e  = pyurdme.Parameter(name="sigma_e",expression="5.58e7/(1000.0*NA)")
        sigma_de = pyurdme.Parameter(name="sigma_de",expression=0.7)
        sigma_dt = pyurdme.Parameter(name="sigma_dt",expression=0.5)
        
        self.add_parameter([NA,sigma_d,sigma_dD,sigma_e,sigma_de,sigma_dt])

        # List of Physical domain markers that match those in the  Gmsh .geo file.
        interior = [1]
        boundary = [2]
        
        # Reactions
        R1 = pyurdme.Reaction(name="R1",reactants={MinD_c_atp:1},products={MinD_m:1},propensity_function="MinD_c_atp*sigma_d/MeshSize", restrict_to=boundary)
        R2 = pyurdme.Reaction(name="R2",reactants={MinD_c_atp:1,MinD_m:1},products={MinD_m:2},massaction=True,rate=sigma_dD)
        R3 = pyurdme.Reaction(name="R3",reactants={MinD_m:1,MinD_e:1},products={MinDE:1},massaction=True,rate=sigma_e)
        R4 = pyurdme.Reaction(name="R4",reactants={MinDE:1},products={MinD_c_adp:1,MinD_e:1},massaction=True,rate=sigma_de)
        R5 = pyurdme.Reaction(name="R5",reactants={MinD_c_adp:1},products={MinD_c_atp:1},massaction=True,rate=sigma_dt)
        
        self.add_reaction([R1,R2,R3,R4,R5])
        
        # Restrict to boundary
        self.restrict(MinD_m,boundary)
        self.restrict(MinDE,boundary)
        
        # Distribute molecules over the mesh according to their initial values
        self.set_initial_condition_scatter({MinD_c_adp:4000})
        self.set_initial_condition_scatter({MinD_e:1000})

        self.timespan(range(900))

