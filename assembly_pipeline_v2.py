from email.mime import base
import sys
import os
from datetime import datetime
import gzip
import re
from matplotlib.colors import from_levels_and_colors
import pandas as pd

# Start by parsing the following command through the terminal, choosing only one option in each case:
# 'python assembly_pipeline_v2.py infile1/folder(???) infile2/none(???) here/there regular/parallel trim/notrim kraken/nokraken ariba/noariba wanted_coverage genome_size pilon/nopilon threads RAM'
# test run:
# python assembly_pipeline_v2.py SRR18825428_1.fastq.gz SRR18825428_2.fastq.gz here regular trim kraken ariba 40 124000000 pilon 0 0

# Snabbare?
# python assembly_pipeline_v2.py SRR18825428_1.fastq.gz SRR18825428_2.fastq.gz here regular trim kraken ariba 40 124000000 pilon 0 0 #SBATCH -p node -n 1

'''OPTIONS'''
# infile1
# - here/there: Where should all outputs be saved? If 'here' a new directory is created in 
# the current directory. If 'there' a path will be asked for.
# - regular/parallel: regular means running only one strain, parallel means running multiple strains
# - trim/notrim: trim means we run fastp, notrim means that we don't
# - kraken/nokraken
# - ariba/noariba
# - wanted_coverage
# - genome_size
# - pilon/nopilon
# - threads
# - RAM


''' Function to create directory where all outputs from the pipeline are placed. 
Date and time specific'''
def directory(date, time, there = False):

    # Change the format of time from eg. 09:13:07.186006 to 09h13m07s
    stringtime = time[:2]+'h'+time[3:5]+'m'+time[6:8]+'s'

    # Choose path of directory
    if there:
        print('You requested to save all output files in another directory.')
        path = input('New path: ')
    else:
        path = os.getcwd()

    # Rename directory with date and time
    namedir = 'assembly_' + date + '_' + stringtime

    finalpath = os.path.join(path, namedir)

    os.mkdir(finalpath)
    
    return finalpath

def currenttime():
    time = str(datetime.time(datetime.now()))
    return time

def shortname(filename):
    short = re.search('[a-zA-Z1-9]+', filename).group()
    return short

def fastp_func(infile1, infile2, common_name):

    loglines = f'Fastp started with {infile1} and {infile2}\n'

    outfile1 = f'out_fastp_{common_name}_1.fq.gz'
    outfile2 = f'out_fastp_{common_name}_2.fq.gz'

    fastpinput = 'fastp -i ' + infile1 + ' -I ' + infile2 + ' -o ' + outfile1 + ' -O ' + outfile2

    os.system(fastpinput)

    loglines += 'Fastp complete. Four output files returned:\n'
    loglines += f'{outfile1} \n{outfile2} \nfastp.html \nfastp.json \n\n'
    return outfile1, outfile2, loglines

def reads_for_coverage(fastq_file, wanted_coverage, genome_size):
    
    loglines = (f'Running: reads_for_coverage')
    loglines += f'Checking if coverage can be achieved \n\n'

    bases_needed = int(wanted_coverage*genome_size/2)
    
    loglines = f'To achieve {wanted_coverage} X, {bases_needed} bases are needed from each fastq-file\n'

    total_bases = 0
    read_counter = 0
    row_counter = 1 # goes between 1 and 4
    
    with gzip.open(fastq_file, 'rt') as file:
        for line in file:
            if '@' in line:
                lenlist = re.findall('(length=[1-9]+)', line)
                if len(lenlist) > 0:
                    lenlist2 = lenlist[0].split('=')
                    readlength = int(lenlist2[1])
                    total_bases += readlength

            elif readlength == 0 and row_counter == 2:
                readlength = len(line)
                total_bases += readlength

            elif row_counter == 4:
                readlength = 0
                read_counter += 1

        # Give log output if the coverage can be achieved
            if total_bases >= bases_needed:
                loglines += f'Needed bases: {bases_needed} (per direction) which amounts to {read_counter} reads from fastq_1 which is {total_bases} bases\n\n'
                coverage = wanted_coverage
                break

            row_counter = row_counter%4 + 1 # makes the counter loop between 1 and 4


    # Give log output if the coverage CANNOT be achieved, and estimate new coverage
    if total_bases < bases_needed:
        loglines += f'There are not enough bases to achieve {wanted_coverage} X coverage.\n\n"'
        available_coverage = int(2*total_bases/genome_size)
        loglines += f'Using an estimated coverage of {available_coverage} X instead which amounts to {read_counter} reads from fastq_1 which is {total_bases} bases\n\n'
        coverage = available_coverage

    reads_needed = read_counter
    
    loglines += f'Function finished.\nOutputs: coverage {coverage}, reads needed {reads_needed}\n\n'

    return coverage, reads_needed, loglines

def shorten_fastq(fastq1_file, fastq2_file, reads_needed, common_name):
    
    loglines = f'shorten_fastq started to shorten {fastq1_file} and {fastq2_file} to only match wanted coverage.\n\n'

    lines_needed = reads_needed*4
    newname1 = f'X_{common_name}_1.fq.gz'
    newname2 = f'X_{common_name}_2.fq.gz'
    
    with gzip.open(fastq1_file, 'rt') as trim_me: # maybe change to 'rb'
        newfile = ''
        for i, line in enumerate(trim_me):
            newfile += line
            if i == lines_needed:
                break
    
    with gzip.open(newname1, 'wt') as one:
        one.write(newfile)

    with gzip.open(fastq2_file, 'rt') as trim_me:
        newfile = ''
        for i, line in enumerate(trim_me):
            newfile += line
            if i == lines_needed:
                break

    with gzip.open(newname2, 'wt') as one:
        one.write(newfile)

    loglines += f'Shortening complete.\nOutputs: {newname1}, {newname2}.\n\n'

    return newname1, newname2, loglines

def spades_func(file1, file2, path_spades, common_name, finalpath): # threads, RAM

    loglines = 'SPAdes started\n'

    # To make sure X_spades output is in the correct output directory
    assembly_path = f'{finalpath}/{common_name}_spades'

    # commandline = '#SBATCH -p node -n 1 \n'
    commandline = f'python {path_spades}/spades.py --careful -o {assembly_path} --pe1-1 {file1} --pe1-2 {file2}'
    os.system(commandline)
    #"spades.py --careful -o $filename1_short\_$wanted_coverage\X_spades --pe1-1 $read1_output --pe1-2 $read2_output -t $threads_available -m $RAM_available"

    # rename from contigs.fasta to fasta
    os.system(f'cp {assembly_path}/contigs.fasta {assembly_path}/{common_name}.fasta')
    loglines += f'"contigs.fasta"-file copied and renamed to be called "{common_name}.fasta"'

    loglines += 'SPAdes finished.\n'
    loglines += f'All output files can be found here: {assembly_path}\n\n'

    return assembly_path, loglines

def pilon_func():
    pass

def info(spades_assembly):
    # Output som pandas table for att satta ihop alla strains till en sammanstalld csv-fil, 
    # och varje strain till var sin csv-fil

    loglines = 'Looking at the metrics of assembly_fasta\n\n'

    number_of_contigs, bases_in_contig, total_bases = 0, 0, 0
    contig_lengths = []
    non_base, number_AT, number_GC = 0, 0, 0, 0
    contigs_over_1000 = 0

    # Loop through and get metrics
    with open(spades_assembly, 'r') as s:
        for line in s:
            if '>' in line:
                number_of_contigs += 1
                total_bases += bases_in_contig

                if bases_in_contig != 0:
                    contig_lengths.append(bases_in_contig)
                    if bases_in_contig >= 1000:
                        contigs_over_1000 += 1

                bases_in_contig = 0 # resets

            else:
                bases_in_contig += len(line)
                for base in line:
                    if base == 'A' or base == 'T':
                        number_AT += 1
                    elif base == 'G' or base == 'C':
                        number_GC += 1
                    else:
                        non_base += 1
    
    loglines += f'The number of contigs: {number_of_contigs}, the total number of bases: {total_bases}\n\n'

    sorted_contig_lengths = contig_lengths.sort()
    longest = sorted_contig_lengths[0]
    loglines += f'Longest contig: {longest}\n'
    loglines += f'Contigs longer than 1 kb: {contigs_over_1000}'

    # N50
    temp = 0
    while temp <= total_bases/2:
        for length in sorted_contig_lengths:
            temp += length
            N_50 = length
    
    loglines += f'N50: {N_50}\n'

    # GC-content
    GC = number_GC/(number_GC + number_AT)*100
    loglines += f'The GC-content of the sequence is {GC}. {non_base} non-base characters were excluded from GC-calculation\n'

    loglines += f'-----------------------Metrics finished-----------------------'

    # PLACE ALL INFO IN PANDAS TABLE
    data = {'Total nr bases': total_bases, 'Nr contigs': number_of_contigs, 'Longest contig': longest, 
    'Nr contigs > 1kb': contigs_over_1000, 'N50':N_50, 'GC-content': GC}

    info_df = pd.DataFrame(data)

    return info_df, loglines


# function that runs multiple strains in parallel. Inputs are all sys.argv[]
# Return lines for logfile?
def parallelize():
    pass

# function that runs everything for only one strain. Inputs are all sys.argv[]
# Return lines for logfile?
def regular():
    pass


def main():

    # os.system('SBATCH -p node -n 1')

    infile1 = sys.argv[1]
    infile2 = sys.argv[2]
    new_location = sys.argv[3] == 'there' # will ask for directory location if True
    parallel = sys.argv[4] == 'parallel' # TO BE MODIFIED to run strains in parallel if True
    run_fastp = sys.argv[5] == 'trim' # will run fastp if True
    kraken = sys.argv[6] == 'kraken'
    ariba = sys.argv[7] == 'ariba'
    wanted_coverage = int(sys.argv[8]) # if wanted coverage == 0, then don't run spades
    genome_size = int(sys.argv[9])
    pilon = sys.argv[10] == 'pilon'
    threads = sys.argv[11]
    RAM = sys.argv[12]

    run_spades = wanted_coverage != 0
    common_name = shortname(infile1) # until here only work if not parallel

    if pilon and run_spades == False: # Since pilon requires spades output, this 
        pilon = False
        pilon_lines = 'Pilon not run since SPAdes was not run'

    ''' -------------------CHANGE !?!?!?!----------------------- '''
# Hardcoded
    path_tools = '/proj/uppmax2022-2-14/private/campy_pipeline/assembly/verktyg'
    path_spades = path_tools + '/SPAdes-3.15.4-Linux/bin'

# Let's start this pipeline!
    time = currenttime()
    date = str(datetime.date(datetime.now()))
    
# make directory for output
    finalpath = directory(date, time, new_location)

# Create log file
    logname = 'logfile'
    log = open(logname, 'w')

    lines = 15*'-' + 'LOGFILE' + 15*'-' + '\n\n'

    lines += f'New directory created with the adress {finalpath}\n'
    lines += f'Directory created at {time} on {date}\n'
    lines += 'All outputs will be saved in the new directory.\n\n'
    log.writelines(lines)

# Run in parallel
    # if parallel:
    # parallelize()

# Fastp
    if run_fastp:
        time = currenttime()+'\n'
        log.writelines(time)

        # infile1 = input('Give the fastq, gzipped forward file you want for fastp: ')
        # infile2 = input('Give the fastq, gzipped reverse file you want for fastp: ')

        outfile1_trim, outfile2_trim, fastp_lines = fastp_func(infile1, infile2, common_name)
        log.writelines(fastp_lines)

        infile1 = outfile1_trim
        infile2 = outfile2_trim

# Kraken
    if kraken:
        time = currenttime()+'\n'
        log.writelines(time)

# Number of reads to match the wanted coverage
    if run_spades:
        time = currenttime()+'\n'
        log.writelines(time)
        coverage, reads_needed, coverage_lines = reads_for_coverage(infile1, wanted_coverage, genome_size)
        log.writelines(coverage_lines)
    else:
        coverage = 0

# Shortening fastq-files if the coverage can be reached with less
    if coverage != wanted_coverage:
        time = currenttime()+'\n'
        log.writelines(time)
       
        outfile1_shorten, outfile2_shorten, shorten_lines = shorten_fastq(infile1, infile2, reads_needed, common_name)
        log.writelines(shorten_lines)
        
        infile1 = outfile1_shorten
        infile2 = outfile2_shorten

# Spades
    if run_spades:
        time = currenttime()+'\n'
        log.writelines(time)

        assembly_path, spades_lines = spades_func(infile1, infile2, path_spades, common_name, finalpath)
        log.writelines(spades_lines)

# Pilon
    time = currenttime()+'\n'
    log.writelines(time)
    pilon_lines += '---Write something here---'

    # input file found here: finalpath/SRR18825428_spades/SRR18825428.fasta

# Info/metrics
    time = currenttime()+'\n'
    log.writelines(time)

    from_spades = f'{assembly_path}/{common_name}.fasta'
    
    info_df, infolines = info(from_spades)

    log.writelines(infolines)
    # If we have multiple info_df then use pd.concat([info_df1, info_df2], axis=0) to stack the 2nd below the 1st.
    # This is useful when running in parallel.
    

# Move files to correct folder
    os.system('mv ' + outfile1_trim + ' ' + outfile2_trim + ' fastp.html fastp.json ' + str(finalpath))
    log.writelines('Trimmed fastp output files moved to directory\n\n')

    os.system(f'mv {outfile1_shorten} {outfile2_shorten} {finalpath}')
    log.writelines(f'Shortened fastq files from shorten_fastq function moved to directory\n\n')

    # OBS OBS convert to csv later instead
    os.system(f'mv {info_df} {finalpath}')
    log.writelines(f'Dataframe moved')

# Close and move the logfile to the correct directory
    log.close()
    os.system('mv logfile '+str(finalpath))
    

if __name__ == '__main__':
    main()  
