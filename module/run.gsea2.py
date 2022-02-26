import os, sys, subprocess
from optparse import OptionParser
from datetime import datetime
import argparse
import shutil
import json
import random
import pandas
import numpy

def main():
	usage="%prog [options]" + "\n"
	ap = argparse.ArgumentParser()
	ap.add_argument("--libdir", action="store",
					dest="libdir", help="Working directory to load support library from.")
	ap.add_argument("--dataset",action="store",dest="dataset",help="Input Expression Dataset.")
	ap.add_argument("--gsdb",action="store",dest="gsdb",help="Gene Set Database File.")
	ap.add_argument("--nperm",action="store",dest="nperm",default=1000,type=int,help="Number of permutations.")
	ap.add_argument("--cls",action="store",dest="cls",help="CLS file.")
	ap.add_argument("--reverse",action="store",dest="reverse",default="False",help="Reverse the phenotype comparison defined in the CLS file.")
	ap.add_argument("--permute",action="store",dest="perm",default="False",help="Reverse the phenotype comparison defined in the CLS file.")
	ap.add_argument("--perm",action="store",dest="perm",default="sample",help="Permutation mode. Options are 'sample' (phenotype) and 'set' (gene set).")
	ap.add_argument("--collapse",action="store",dest="collapse",default="none",help="Method for computing mathematical collapse. Supports 'none' ('no collapse'), 'sum', 'mean', 'median', 'max', 'absmax'")
	ap.add_argument("--chip",action="store",dest="chip",default="none",help="Chip file used for performing collapse.")
	ap.add_argument("--metric",action="store",dest="rank_metric",help="Metric for ranking genes.")
	ap.add_argument("--method",action="store",dest="method",help="Enrichment Method. 'ks' (old GSEA) and 'js' (next gen GSEA) supported.")
	ap.add_argument("--weight",action="store",dest="weight",default=1.0,type=float,help="Weight for ks or auc enrichment method.")
	ap.add_argument("--max",action="store",dest="max",default=500,type=int,help="Max gene set size.")
	ap.add_argument("--min",action="store",dest="min",default=15,type=int,help="Min gene set size.")
	ap.add_argument("--seed",action="store",dest="seed",default="timestamp",help="Random seed used for permutations.")
	ap.add_argument("--ogllv",action="store",dest="override",default="False",help="Override reasonableness check for input dataset gene list size.")
	ap.add_argument("--nplot",action="store",dest="nplot",default=25,type=int,help="Number of enrichment results to plot.")
	ap.add_argument("--cpu",action="store",dest="cpu",default=1,type=int,help="Job CPU Count.")
	options = ap.parse_args()

	sys.path.insert(1, options.libdir)
	import GSEAlib

	## Generate and set the random seed at the Python level and save it to pass to GSEA
	if options.seed == "timestamp":
		options.seed = int(round(datetime.now().timestamp()))
		random.seed(options.seed)
	else:
		options.seed = int(rouns(options.seed))
		random.seed(options.seed)

	os.mkdir("gsea_results")
	os.mkdir("gsea_results/input")


	## Parse GMT/GMX files from a list of inputs and create a name:members dict written out as a json file
	if options.gsdb != None:
		with open(options.gsdb) as f:
			gene_sets_dbfile_list = f.read().splitlines()

	genesets, genesets_descr=GSEAlib.read_sets(gene_sets_dbfile_list)
	with open('gsea_results/input/set_to_genes.json', 'w') as path:
		json.dump(genesets, path,  indent=2)


	## Parse GCT file
	if options.dataset.split(".")[-1] == "gct":
		if options.collapse != "none":
			chip_file=GSEAlib.read_chip(options.chip)
			input_ds = GSEAlib.collapse_dataset(options.dataset, chip_file, method=options.collapse)
		else:
			input_ds = GSEAlib.read_gct(options.dataset)
		input_ds=input_ds['data']
	else:
		input_ds=pandas.read_csv(options.dataset, sep='\t', index_col=0, skip_blank_lines=True)
		if "description" in input_ds.columns.str.lower():
			description_loc=input_ds.columns.str.lower().to_list().index('description')
			input_ds.drop(input_ds.columns[[description_loc]], axis = 1, inplace = True)
			input_ds.index.name="Name"
		if options.collapse != "none":
			chip_file=GSEAlib.read_chip(options.chip)
			input_ds = GSEAlib.collapse_dataset(input_ds, chip_file, method=options.collapse)
			input_ds=input_ds['data']

	if len(input_ds)<10000 and options.override=="False":
		sys.exit(print("Only ", len(imput_ds), "genes were identified in the dataset.\nEither the dataset did not contain all expressed genes, or there was possibly a problem with the chip selected for collapse dataset.\n\nIf this was intentional, to bypass this check you can set 'override gene list length validation' (--ogllv) to 'True' but this is not recommended."))
	if len(input_ds)<10000 and options.override=="True":
		print("Only", len(input_ds), "genes were identified in the dataset, but the user specified overriding this check. Continuing analysis, as-is however this is not recommended. The input dataset should include all expressed genes.")

	## Parse CLS file
	phenotypes=GSEAlib.read_cls(options.cls)
	phenotypes=GSEAlib.match_phenotypes(input_ds,phenotypes)
	if options.reverse=="True" and phenotypes.columns[0]=="Labels":
		phenotypes["Phenotypes"]=numpy.where((phenotypes["Phenotypes"]==0)|(phenotypes["Phenotypes"]==1), phenotypes["Phenotypes"]^1, phenotypes["Phenotypes"])
	phenotypes=phenotypes.sort_values('Phenotypes')

	## Order the dataset using the phenotypes and write out both files
	input_ds=input_ds.reindex(columns=phenotypes.index)
	input_ds.to_csv('gsea_results/input/gene_by_sample.tsv', sep = "\t")
	pandas.DataFrame(phenotypes['Phenotypes']).transpose().to_csv('gsea_results/input/target_by_sample.tsv',sep="\t", index=False)

	## Construct GSEA Settings json file
	gsea_settings={
		"number_of_permutations": options.nperm,
		"permutation": options.perm,
		"metric": options.rank_metric,
		"algorithm": options.method,
		"weight": options.weight,
		"maximum_gene_set_size": options.max,
		"minimum_gene_set_size": options.min,
		"remove_gene_set_genes": True,
		"random_seed": options.seed,
		"number_of_jobs": options.cpu,
		"number_of_extreme_gene_sets_to_plot": options.nplot,
		"gene_sets_to_plot": []
	}

	with open('gsea_results/input/gsea_settings.json', 'w') as path:
		json.dump(gsea_settings, path,  indent=2)

	## Run GSEA
	subprocess.check_output(['gsea', 'standard', 'gsea_results/input/gsea_settings.json', 'gsea_results/input/set_to_genes.json', 'gsea_results/input/target_by_sample.tsv', 'gsea_results/input/gene_by_sample.tsv', 'gsea_results'])

	## Parse Results
	genesets_descr=pandas.DataFrame.from_dict(genesets_descr,orient="index",columns=["URL"])
	results=GSEAlib.result_paths('gsea_results')
	plots=[result for result in results if "plot" in result]
	gsea_stats=pandas.read_csv('gsea_results/float.set_x_statistic.tsv',sep="\t",index_col=0)

	#Positive Enrichment Report
	gsea_pos=gsea_stats[gsea_stats.loc[:,"Enrichment"]>0]
	gsea_pos=genesets_descr.merge(gsea_pos, how='inner',left_index=True, right_index=True).sort_values(["Q-value","P-value","Enrichment"],0,ascending=(True,True,False)).reset_index().rename(columns={'index':'Gene Set'})
	gsea_pos["Gene Set"] = gsea_pos.apply(lambda row: "<a href='{}' target='_blank'>{}</a>".format(row.URL, row['Gene Set']), axis=1)
	gsea_pos.drop("URL",axis=1,inplace=True)
	gsea_neg=gsea_pos.reindex(list(range(1,len(gsea_pos))),axis=0)
	gsea_pos.to_html(open('positve_enrichment.html', 'w'),render_links=True,escape=False)

	#Negative Enrichment Report
	gsea_neg=gsea_stats[gsea_stats.loc[:,"Enrichment"]<0]
	gsea_neg=genesets_descr.merge(gsea_neg, how='inner',left_index=True, right_index=True).sort_values(["Q-value","P-value","Enrichment"],0,ascending=(True,True,True)).reset_index().rename(columns={'index':'Gene Set'})
	gsea_neg["Gene Set"] = gsea_neg.apply(lambda row: "<a href='{}' target='_blank'>{}</a>".format(row.URL, row['Gene Set']), axis=1)
	gsea_neg.drop("URL",axis=1,inplace=True)
	gsea_neg=gsea_neg.reindex(list(range(1,len(gsea_neg))),axis=0)
	gsea_neg.to_html(open('negative_enrichment.html', 'w'),render_links=True,escape=False)


if __name__ == '__main__':
	main()
