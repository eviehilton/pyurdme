/* Stand-alone nsm2 solver for use with URDME. */

/* 
   A. Hellander and B. Drawert 2012-06-15 (Revision)
   P. Bauer and S. Engblom 2012-05-04 (Revision) 
   A. Hellander 2009-11-24 
*/

#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "propensities.h"
#include "nsm2.h"
#include "urdmemodel.h"
#include "outputwriter.h"
#include "time.h"

#include "hdf5.h"
#include "hdf5_hl.h"

#ifndef URDME_LIBMAT
#include "mat.h"
#include "mex.h"
#else
#include "read_matfile.h"
#endif


/* 
 
Input:
 
 model.nsm2 input_file.mat outputfile.mat seed param_case
 
 input_file:  model file generated by Matlab interface.
 
 output_file: name of output file
 
 seed: seed passed on the command line. Overrides a seed from the input file. This 
       argument is never used by the interactive matlab interface, but may be used
       when executed in a diostributed environment. 
 
 param_case: which parameter set to use. Relevant if a matrix with parameters is provided in the 
             input file. This is a new feature in urdme 1.2, and has beta-status. 
 
*/


int main(int argc, char *argv[])

{
	
	char *infile,*outfile;
	int i, nt=1, report_level;

	
	if (argc < 3) {
        perror("Too few arguments to nsm2.\n");
        return -1;
    }
	
	/* Input file. */
	infile  = argv[1];
    
	/* Output file */
	outfile = argv[2];
	
	/* Read model specification */
	urdme_model *model;
	model = read_model(infile);
	model->infile = infile;
	
	if (model == NULL) {
        perror("Fatal error. Failed to load model file.\n");
        return -2;
    }
    
	/* Check model file for optional report level and seed. */ 
	MATFile *input_file;
	input_file = matOpen(infile,"r"); 
    
	mxArray *mxreport;
    if (input_file == NULL) {
        perror("Fatal error. Failed to load model file.\n");
        return -2;
    }
	mxreport = matGetVariable(input_file, "report");
    //mxInfo(mxreport);
	if (mxreport != NULL) {
		report_level = (int) mxGetScalar(mxreport);
        //printf("mxreport is not NULL, report_level=%i\n",report_level);
	}else{
        report_level=1;	
        //printf("mxreport is NULL, report_level=%i\n",report_level);
    }
	model->num_extra_args=1;
    
	/* Look for seed */
    mxArray *mxseed;
	mxseed = matGetVariable(input_file, "seed");
    if(mxseed!=NULL && (!mxIsEmpty((mxseed)))) {
        srand48((long int)mxGetScalar(mxseed));
    } else {
      srand48((long int)time(NULL)+(long int)(1e9*clock()));	
    }
	/* 
       If seed is provided as a parameter, it takes precedence. 
       We need to be able to pass the seed as a paramters as well
       as in the input file in the cases where the solver is run
       in a distributed environment. 
    */
	if (argc > 3) {
		srand48((long int)atoi(argv[3]));  
	}
	
	/* Look for an optional parameter matrix. */
	const double *matfile_parameters; 
	int mpar = 0;
	int npar = 0;
	int param_case=1;
	
    mxArray *mxparameters;
	mxparameters = matGetVariable(input_file, "parameters");
    if (mxparameters != NULL) {
		matfile_parameters = (double *)mxGetPr(mxparameters);
		mpar = mxGetM(mxparameters);
		npar = mxGetN(mxparameters); 
	}
    
	/* Look if a parameter case if supplied as a parameter. */
	if (argc > 4) {
	    param_case = (int)atoi(argv[4]);
	}
	
	if (param_case > npar && mxparameters!=NULL) {
		perror("nsm2core: Fatal error, parameter case is larger than n-dimension in parameter matrix.\n");
		exit(-2);
	}
	
	/* Create global parameter variable for this parameter case. */
    parameters = (double *)malloc(mpar*sizeof(double));
    memcpy(parameters,&matfile_parameters[mpar*(param_case-1)],mpar*sizeof(double));
    
	/* Set report level */
	model->extra_args=malloc(model->num_extra_args*sizeof(void *));
	for (i=0;i<model->num_extra_args;i++)
		model->extra_args[i]=NULL;
	model->extra_args[0] = malloc(sizeof(int));
	*(int *)(model->extra_args[0]) = report_level;

	/* Allocate memory to hold nt solutions. */
	init_sol(model,nt);
    //model->nsol=0
    
  
    /* Get a writer to store the output trajectory on a hdf5 file. */
    urdme_output_writer *writer;
    writer = get_urdme_output_writer(model,outfile);
    
	/* Call nsm2-solver: get a trajectory and add it to the output file. . */
    nsm2(model, writer);
    
    /* Write the timespan vector to the output file */
    write_tspan(writer,model);

    /* free memory allocated by mxGetVariable. */
    mxDestroyArray(mxreport);
	mxDestroyArray(mxseed);
    mxDestroyArray(mxparameters);

    matClose(input_file);
    free(parameters);
    
    destroy_output_writer(writer);
    destroy_model(model);
	
	return(0);
	
}

/* Wrapper for the nsm2 solver. */
void nsm2(void *data, urdme_output_writer *writer){
    
	/* Unpack input */
	urdme_model* model;
	model = (urdme_model *)data;
	int Ndofs;
	
	/* nsm2_core() uses a report function with optional report level. This is
	 passed as the first extra argument. */ 
	int report_level = *(int *)model->extra_args[0];
	
	/* Output array (to hold a single trajectory) */
	Ndofs = model->Ncells*model->Mspecies;
	
    /* Core simulation routine. */
	nsm2_core(model->irD, model->jcD, model->prD,
              model->u0,
			  model->irN, model->jcN, model->prN,
              model->irG, model->jcG,
              model->tspan, model->tlen,
			  model->vol, model->data, model->sd,
              model->Ncells,
              model->Mspecies, model->Mreactions,
              model->Msubdomains,
              model->dsize, report_level,
			  model->irK, model->jcK, model->prK,
              model->R, model->I, model->S,
              writer);
    
	
		
}


 