import pyurdme
import dolfin
import os
import tempfile
import subprocess
import shutil
import numpy
from pyurdme import get_N_HexCol
import json
import uuid
import h5py
import math 

try:
    # This is only needed if we are running in an Ipython Notebook
    import IPython.display
except:
    pass

class InvalidModelException(Exception):
    """Base class for exceptions in this module."""
    pass

class MMMSSolver(pyurdme.URDMESolver):
    """ Mesoscopic-microscopic hybrid solver.

        TODO: Description. 

    """
    
    NAME = 'mmms'
    
    def __init__(self, model, solver_path=None, report_level=0, model_file=None, sopts=None,model_level_mapping=None, min_micro_timestep=1e-4,hybrid_splitting_timestep=5e-6):
        pyurdme.URDMESolver.__init__(self,model,solver_path,report_level,model_file,sopts)

        self.solver_name = 'hybrid'
        self.solver_path = ''
        self.urdme_infile_name = ''

        # Default settings for hybrid simulations
        self.model_level_mapping = None
        self.set_modeling_level(model_level_mapping=model_level_mapping)

        self.hybrid_splitting_timestep = hybrid_splitting_timestep
        self.set_minimial_micro_timestep(min_micro_timestep)

    
    def __getstate__(self):
        """ TODO: Implement"""
    
    def __getstate__(self):
        """ TODO: Implement"""
    
    def __del__(self):
        """ Remove the temporary output folder """
        if self.delete_infile:
            try:
                os.remove(self.infile_name)
            except OSError as e:
                print "Could not delete '{0}'".format(self.infile_name)
    #shutil.rmtree(self.outfolder_name)

    def set_minimial_micro_timestep(self, timestep):
        self.min_micro_timestep = timestep
    
    def set_modeling_level(self, model_level_mapping=None):

        ml = {"meso":1,"micro":0}
        species = self.model.listOfSpecies
        mlmap = {}

        # As deafult, set all species to "micro"
        if self.model_level_mapping  == None and model_level_mapping == None:
            for spec_name, x  in species.iteritems(): 
                mlmap[spec_name] = ml["micro"]
        else:
            for spec_name, model_level in model_level_mapping.iteritems():
                if not spec_name in species:
                    raise Exception("Failed to set modeling level, no such species in model: {0}".format(spec_name)) 
                try:
                    mlmap[spec_name] = ml[model_level]
                except KeyError, e:
                    raise Exception("Not a valid modeling level."+e)
        self.model_level_mapping = mlmap

    def F(x):
        f = (4*math.log(1/x)-(1-x*x)*(3-x*x))/(4*(1-x*x)*(1-x*x))
        return f

    def ka_hhp2D(self, rho,vol,gamma,kr):
        """ Calculate the HHP reaction rate in 2D. """
        R = math.sqrt(vol/math.pi)
        lam = rho/R
        alpha = kr/(2*math.pi*gamma)
        return math.pi*R*R/kr*(1+alpha*F(lam))

    def ka_ck(self, rho, gamma, kr):
        """ Calculate the Collins-Kimball reaction rate """
        ka_ck = 4.0*math.pi*rho*gamma*kr/(4.0*math.pi*rho*gamma+kr)
        return ka_ck

    def ka_hhp3D(self, rho, gamma, kr, vol):
        """ Calulate the HHP mesoscopic reaction rate in 3D. """
        h = math.pow(vol,1.0/3.0)
        G = 1.0/(4*math.pi*rho)-1.5164/(6*h)
        ka = kr/(vol*(1.0+kr/gamma*G))
        return ka

    def estimate_relative_error_in_reaction(self, reaction, vol):
        """ Compute the relative error. """ 
        ka =  reaction.marate.value
        gamma = 0.0
        rho   = 0.0
        for Sname in reaction.reactants:
            S = self.model.listOfSpecies[Sname]
            rho += S.reaction_radius
            gamma += S.diffusion_constant

        ka_meso = self.ka_hhp3D(rho, gamma, ka,vol)
        W  = ka/(vol*ka_meso) - 1.0
        return W 


    def propose_mesh_resolution_per_reaction(self, rel_tol=0.025):

        reactions = self.model.listOfReactions
        res = {}
        for Rname, R in reactions.iteritems(): 
            # Bimolecular reactions are affected
            if len(R.reactants) == 2:
                mz  = self.estimate_mesh_resolution(reaction=R, rel_tol=rel_tol)
                res[Rname]=mz
        return res

    def estimate_mesh_resolution(self, reaction=None, rel_tol=None):
        """ Compute a mesh resolution that satiesfies rel_tol relative tolerance
            for all bimolecular reactions. """

        # Initial guess
        sigma_max = 0.0
        for s_name, spec in self.model.listOfSpecies.iteritems():
            if sigma_max < spec.reaction_radius:
                sigma_max = spec.reaction_radius
        h = 40*sigma_max     

        W_max  = 100
        while W_max > rel_tol:

            if h < 3.2*sigma_max:
                h = 3.2*sigma_max

            W_max = 0.0

            # Bimolecular reactions are affected
            if len(reaction.reactants) == 2:
                W = self.estimate_relative_error_in_reaction(reaction, math.pow(h,3))
                if W > W_max:
                    W_max = W

            if h < 3.2*sigma_max:
                break
            else:
                h = 0.9*h
    
        return (h, W_max)

    def predict_mesoscale_simulation_time(self, mesh_size):
        """  Predict the simulation time of the RDME solver for the current
             model and solver setting. """

        # Hmm, this is probably not going to work

        # TODO: This parameter needs to be obtained from a (one-time per platform) profiling step 
        diffusion_events_per_second = 10^6


    def partition_system(self, rel_tol=0.025):
        """ Compute an initial system partitioning given the relative tolerance rel_tol. """

        reactions = self.model.listOfReactions
        for Rname, R in reactions.iteritems(): 
            # Bimolecular reactions are affected
            if len(R.reactants) == 2:
                W = self.estimate_relative_error_in_reaction(R, math.pow(self.model.voxel_size,3))
                print W

    def _write_mesh_file(self, filename=None):
        """ Write the mesh data to a HDF5 file. """
        
        meshfile = h5py.File(filename,"w")
        meshfile.create_group("mesh")
        meshfile.create_group("boundarymesh")
        grp = meshfile["mesh"] 
    
        mesh = self.model.mesh
        mesh.init()
        
        cells = mesh.cells()
        grp.create_dataset("t", data = cells)
        vertices = mesh.coordinates()
        grp.create_dataset("p",data=vertices)

        # Create the bounday mesh triangle entities 
        boundary_mesh = dolfin.BoundaryMesh(mesh, "exterior")

        #print numpy.shape(boundary_mesh.coordinates())
       # print numpy.shape(boundary_mesh.cells())
    
        # Vertex map
        vm = boundary_mesh.entity_map(0).array()
        #print vm
        
        bndtri= []
        for tri in boundary_mesh.cells():
            bndtri.append([vm[v] for v in tri])

        grp.create_dataset("boundaryfacets",data=numpy.array(bndtri))

        # Datastructure, vertex->tetrahedron
        mesh.init(0,0)
        f = dolfin.MeshEntity(mesh, 0,0)
        v2t = []
        for v in dolfin.vertices(mesh):
            #for c in dolfin.cells(v):
            v2t.append([ci.index() for ci in dolfin.cells(v)])
                #print v.index(), c.index()
        v2t = numpy.array(v2t)        
        lmax = 0;
        for l in numpy.array(v2t):
            if len(l) > lmax:
                lmax = len(l)
        temp = -1*numpy.ones((len(v2t),lmax))

        for i,l in enumerate(v2t):
            for j,v in enumerate(l):
                temp[i,j] = v;

        grp.create_dataset("vertex2cells",data=temp)       
        meshfile.close()

        #for cell in dolfin.cells(mesh):
        #    for face in dolfin.faces(cell):
        #        print [v for v in face.entities(0)] 
        
        #print cells
        #D = mesh.topology().dim()
        #fct = dolfin.facets(mesh)

        #edges = []
        #for facet in fct:
        #   edges.append([v for v in facet.entities(D)])
        #print numpy.array(edges)

        #grp.create_dataset("edges",data=numpy.array(edges))
     
    def create_input_file(self, filename):
        """ Write a model input file for the MMMS solver, new format  """ 
        with open(filename, "w") as fh:
            fh.write(json.dumps(self.model, cls=ModelEncoder))

    def create_input_file_old(self, filename):
        """  Write a model input file for the MMMS solver, old format. """
    
        input_file = open(filename,'w')
        input_file.write("NAME "+self.model.name+"\n")
        
        
        # Write the model dimension
        (np,dim) = numpy.shape(self.model.mesh.coordinates())
        input_file.write("DIMENSION {0}\n".format(dim))
        input_file.write("BOUNDARY 0 0.7 0 0.7 0 0.7\n")
        
        self.model.resolve_parameters()
        params = ""
        for i, pname in enumerate(self.model.listOfParameters):
            P = self.model.listOfParameters[pname]
            params += "PARAMETER {0} {1}\n".format(pname, str(P.value))
        input_file.write(params)

        speciesdef = ""
        
        initial_data = self.model.u0
        spec_map = self.model.get_species_map()
        
        for i, sname in enumerate(self.model.listOfSpecies):
            S = self.model.listOfSpecies[sname]
            ml = self.model_level_mapping[sname]
            sum_mol = numpy.sum(self.model.u0[spec_map[sname],:])
            speciesdef += "SPECIES {0} {1} {2} {3} {4}\n".format(sname, str(S.diffusion_constant), str(S.reaction_radius), sum_mol, ml)
            
        input_file.write(speciesdef)
    
        reacstr = ""
        for i, rname in enumerate(self.model.listOfReactions):
            R = self.model.listOfReactions[rname]
            reacstr += "REACTION "

            for j, reactant in enumerate(R.reactants):
                reacstr += str(reactant)+" "
            
            reacstr += "> "
            
            for j, product in enumerate(R.products):
                reacstr += str(product)+" "

            try: 
                reacstr += " {0}\n".format(str(R.marate.value))
            except AttributeError: 
                raise InvalidModelException("Invalid model. The hybrid solver only supports mass action propensities (mass_action=True)")

        input_file.write(reacstr)

        input_file.write("T {0}\n".format(str(self.model.tspan[-1])))
        nint = len(self.model.tspan)
        input_file.write("NINT {0}\n".format(str(int(nint))))

    def run(self, number_of_trajectories=1, seed=None, input_file=None, loaddata=False):
        """ Run one simulation of the model.
            
            number_of_trajectories: How many trajectories should be run.
            seed: the random number seed (incremented by one for multiple runs).
            input_file: the filename of the solver input data file .
            loaddata: boolean, should the result object load the data into memory on creation.
            
            Returns:
            URDMEResult object.
            or, if number_of_trajectories > 1
            a list of URDMEResult objects
        """
        
        # Create the urdme input file that contains connectivity matrices etc
        if self.urdme_infile_name is None or not os.path.exists(self.urdme_infile_name):
            # Get temporary input and output files
            urdme_infile = tempfile.NamedTemporaryFile(delete=False, dir=os.environ.get('PYURDME_TMPDIR'))
                
            # Write the model to an input file in .mat format
            self.serialize(filename=urdme_infile, report_level=self.report_level)
            urdme_infile.close()
            self.urdme_infile_name = urdme_infile.name
            self.delete_infile = True

        if not os.path.exists(self.urdme_infile_name):
            raise URDMEError("input file not found.")
        
        # Generate the input file containing the microsolver specific information
        infile = tempfile.NamedTemporaryFile(delete=False, dir=os.environ.get('PYURDME_TMPDIR'))
        self.infile_name = infile.name
        self.create_input_file(infile.name)

    
        infile.close()

        # Create the mesh input file
        mesh_infile = tempfile.NamedTemporaryFile(delete=False, dir=os.environ.get('PYURDME_TMPDIR'))
        self._write_mesh_file(mesh_infile.name)
        self.mesh_infile_name=mesh_infile.name
        mesh_infile.close()

        if not os.path.exists(self.mesh_infile_name):
            raise URDMEError("Mesh input file not found.")
        
        # Generate output file
        outfile = tempfile.NamedTemporaryFile(delete=False, dir=os.environ.get('PYURDME_TMPDIR'))
        outfile.close()        
        
        if self.report_level > 2:
            print model_str
        if number_of_trajectories > 1:
            result_list = []

        solver_str=os.path.dirname(__file__)+"/mmms/bin/mmms"

        solver_cmd = [solver_str,self.infile_name, self.urdme_infile_name,self.mesh_infile_name, outfile.name]
        
        handle = subprocess.Popen(solver_cmd)#, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        handle.wait()
        
        try:
            result = MICROResult(self.model,outfile.name)
            return result
        except:
            print handle.stderr.read()
            raise

class MICROResult():

    def __init__(self,model, filename=None):
        self.filename=filename
        self.model = model
    
    def get_particles(self,species, time_index):
        """ Return a dict with the unique ids and positions of all particles of type species
            at time point time. """

        file = h5py.File(self.filename,'r')
        return {
                'unique_ids':numpy.array(file.get("Trajectories/0/Type_{0}/unique_ids_{1}".format(species, time_index))),
                'positions':numpy.array(file.get("Trajectories/0/Type_{0}/positions_{1}".format(species,time_index)))
                }

    def get_species(self,spec_name, time_index):
        """ Return copy number of spec_name in each voxel of the mesh. This function mimics the
            functionality of the mesoscopic solvers, so we insert particles in the voxels
            based on their position.  """

        return None
        #with open(self.output_folder_name+"/0_pos.txt", 'r') as fh:
        #    print fh.read()

    def get_summary_statistic(self, species, time_indices=None):
        """ Return the sum of molecules of a species for set of time points.
            If the result file contains multiple trajectories, then the 
            mean is taken over the realizations. 

            TODO: Implement mean value. 

        """
        
        if time_indices == None:
            tind = range(len(self.model.tspan))

        num_mol = []
        for ti in tind:
            r = self.get_particles(species, ti)
            (nm,dim) = numpy.shape(r['unique_ids'])
            num_mol.append(nm)

        return numpy.array(num_mol)

    def _export_to_particle_js(self,species,time_index, colors=None):
        """ Create a html string for displaying the particles as small spheres. """
        import random
        with open(os.path.dirname(pyurdme.__file__)+"/data/three.js_templates/particles.html",'r') as fd:
            template = fd.read()
        
        
        x=[]
        y=[]
        z=[]
        c=[]
        radius = []
        
        if colors == None:
            colors =  get_N_HexCol(len(species))
        
 
        spec_map = self.model.get_species_map()

        for j,spec in enumerate(species):
            spec_ind=spec_map[spec]
            particles = self.get_particles(spec_ind, time_index)
            vtx = particles['positions']
            maxvtx = numpy.max(numpy.amax(vtx,axis=0))
            factor = 1/maxvtx
            vtx = factor*vtx
            centroid = numpy.mean(vtx,axis=0)
            # Shift so the centroid is now origo
            normalized_vtx = numpy.zeros(numpy.shape(vtx))
            for i,v in enumerate(vtx):
                normalized_vtx[i,:] = v - centroid
            vtx=normalized_vtx

            for v in vtx:
                    x.append(v[0])
                    y.append(v[1])
                    z.append(v[2])
                    c.append(colors[j])
                    radius.append(0.01)
        
        template = template.replace("__X__",str(x))
        template = template.replace("__Y__",str(y))
        template = template.replace("__Z__",str(z))
        template = template.replace("__COLOR__",str(c))
        template = template.replace("__RADIUS__",str(radius))
        
        return template


    def display_particles(self,species, time_index, width=500):
        hstr = self._export_to_particle_js(species, time_index)
        displayareaid=str(uuid.uuid4())
        hstr = hstr.replace('###DISPLAYAREAID###',displayareaid)
	hstr = hstr.replace('###WIDTH###',str(width))
        height = int(width*0.75)        
        html = '<div id="'+displayareaid+'" class="cell"></div>'
        IPython.display.display(IPython.display.HTML(html+hstr))

    def __del__(self):
        """ Deconstructor. """
            #   if not self.data_is_loaded:
        try:
            # Clean up data file
            os.remove(self.filename)
        except OSError as e:
            #print "URDMEResult.__del__: Could not delete result file'{0}': {1}".format(self.filename, e)
            pass

class ModelEncoder(json.JSONEncoder):
    """ Encoder for an URDMEModel """ 

    def default(self, obj):

        if isinstance(obj,pyurdme.URDMEModel):

            model_doc = {}
            spec_list = []
            for name, species in obj.listOfSpecies.iteritems():
                spec_list.append(species.__dict__)
            model_doc["species_list"] = spec_list

            parameter_list = []
            for name, parameter in obj.listOfParameters.iteritems():
                #print parameter.__dict__
                parameter_list.append(parameter.__dict__)
            model_doc["parameter_list"] = parameter_list

            reaction_list = []
            for name, reaction in obj.listOfReactions.iteritems():
                reaction_doc  = reaction.__dict__
                if "marate" in reaction_doc:
                    param = reaction_doc.pop("marate")
                    reaction_doc["marate"] = param.name
                reaction_list.append(reaction_doc)

            model_doc["reaction_list"] = reaction_list

            return model_doc

        return json.JSONEncoder.default(self, obj)



