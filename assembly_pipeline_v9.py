from datetime import datetime
import gzip
import pandas as pd
import os
import re
import sys
import concurrent.futures as future
import glob



# Start by parsing the following command through the terminal, choosing only one option in each case:
# 'python assembly_pipeline_v8.py infile1/directory infile2/None(???) here/there trim/notrim kraken/nokraken ariba/noariba wanted_coverage genome_size pilon/nopilon threads'

# test run, regular
# python assembly_pipeline_v8.py SRR18825428_1.fastq.gz SRR18825428_2.fastq.gz here trim kraken noariba [vfdb_core] 40 1743985 nopilon 40

# parallelize
# python assembly_pipeline_v8.py manyfiles None here trim kraken noariba [vfdb_core] 40 1743985 nopilon 40

# Lokal Alma:
# python Pipeline/assembly_pipeline_v8.py /home/alma/Documents/kandidat/genomes/SRR18825428_1.fastq.gz /home/alma/Documents/kandidat/genomes/SRR18825428_2.fastq.gz here ntrim nkraken ariba [vfdb_core] 0 1743985 npilon 0



'''OPTIONS'''
# - infile1 / directory: enter a directory to multiple short read files to run the pipeline in 
# parallel. Will use same wanted coverage, however!
# - infile2 / None: enter None if a directory was entered as infile1.
# - here/there: Where should all outputs be saved? If 'here' a new directory is created in 
# the current directory. If 'there' a path will be asked for.
# - trim/notrim: trim means we run fastp, notrim means that we don't.
# - kraken/nokraken: choose whether kraken should be run or not.
# - ariba/noariba: choose whether to align AMR-genes with ariba.
# - [vfdb_core]: list of AMR-databases for ariba, without spaces.
# - wanted_coverage: what coverage is requested? If 0, no assembly is performed.
# - genome_size: what is the genome size of the organism?
# - pilon/nopilon: choose whether to run pilon or not. Does not run if spades does not run (0 wanted coverage)
# - threads: maximum threads available.

def directory(date, time, there = False):
    
    ''' Function to create directory where all outputs from the pipeline are placed. 
    Date and time specific'''

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
    '''Function that returns a string with the current time.'''
    time = str(datetime.time(datetime.now()))
    return time

def shortname(filename):
    '''Function that take a filename and returns a shorter version 
    including only the first continuous word-number sequence.'''
    splitit = filename.split('/')
    name = splitit[-1]
    short = re.search('[a-zA-Z1-9]+', name).group()
    return short

def create_log(finalpath, time, date, logname):

    lines = 15*'-' + 'LOGFILE' + 15*'-' + '\n\n'
    lines += f'Pipeline called with following arguments:\n'
    lines += f'\t infile1: {infile1}, infile2: {infile2}, new_location: {new_location},\n'
    lines += f'\t run_fastp: {run_fastp}, kraken: {kraken}, ariba: {ariba}, db_ariba: {db_ariba}, wanted_coverage: {wanted_coverage},\n'
    lines += f'\t genome_size: {genome_size}, pilon: {pilon}, threads: {threads}\n\n'
    lines += f'The following packages and versions used:\n'
    lines += os.popen("conda list | awk '/^python /{print $1\"\t\"$2}'").read().strip() + '\n'
    lines += os.popen("conda list | awk '/^fastp /{print $1\"\t\"$2}'").read().strip() + '\n'
    lines += os.popen("conda list | awk '/^kraken2 /{print $1\"\t\"$2}'").read().strip() + '\n'
    lines += os.popen("conda list | awk '/^spades /{print $1\"\t\"$2}'").read().strip() + '\n'
    lines += os.popen("conda list | awk '/^bowtie2 /{print $1\"\t\"$2}'").read().strip() + '\n'
    lines += os.popen("conda list | awk '/^ariba /{print $1\"\t\"$2}'").read().strip() + '\n\n'
    lines += f'New directory created with the adress {finalpath}\n'
    lines += f'Directory created at {time} on {date}\n'
    lines += 'All outputs will be saved in the new directory.\n\n'
    os.system(f"echo '{lines}' > {logname}")
    
    return

def log_parse(string, logpath = ''):
    time = currenttime()
    os.system(f"echo {time}: '{string}\n' >> {logpath}/{logname}")
    
    return

def ariba_fun(path, infile1,infile2,db_ariba):
    # Functional db: argannot, vf_core, card, resfinder, srst2_argannot, plasmidfinder, virulencefinder  
    # Nonfunctional: ncbi och vfdb_full 
    
    os.chdir(base_dir)

    for db_name in db_ariba: 
        log_parse(f' Starting ariba with {db_name}', path)
        if os.path.exists(f'out.{db_name}.fa'): 
            log_parse(f'Database {db_name} already downloaded', path)
            os.system(f"rm -rf out.run.{db_name}") # OBS FARLIGT? är detta smart sätt att göra det? Ska det läggas till i log?

        else: # if database not downloaded.
            os.system(f"rm -rf out.{db_name}*") # DURING PARAL. THIS MIGHT BE AN ISSUE, PERHAPS SHOULD CREATE UNIQUE NAME? OR MOVE DIRCTLY INTO DIR
            log_parse(f'Downloading database {db_name}', path)
            os.system(f"ariba getref {db_name} out.{db_name} >> {logname}")

            log_parse(f'Preparing references with prefix out.{db_name}', path)
            os.system(f"ariba prepareref -f out.{db_name}.fa -m out.{db_name}.tsv out.{db_name}.prepareref >> {logname}")

        os.chdir(path) # go to output path
        
        log_parse(f'Running ariba on {db_name}', path)
        os.system(f"ariba run {base_dir}/out.{db_name}.prepareref {infile1} {infile2} out.run.{db_name} >> {logname}")

    log_parse(f'Ariba done.\n', path)
    return

def fastp_func(path, infile1, infile2, common_name):
    '''Function that takes two raw reads fastq files, one forward (1, right) and one reverse(2, left)
    and returns two trimmed fastq files as well as quality control documentation.'''
    os.chdir(path)

    log_parse(f'Fastp started with {infile1} and {infile2}\n', path)

    outfile1 = f'out_fastp_{common_name}_1.fq.gz'
    outfile2 = f'out_fastp_{common_name}_2.fq.gz'

    fastpinput = f'fastp -i {infile1} -I {infile2} -o {outfile1} -O {outfile2}'

    os.system(f'{fastpinput} >> {logname}')
    
    log_parse(f'Fastp complete. Four output files returned:\n{outfile1} \n{outfile2} \nfastp.html \nfastp.json \n', path)
    
    return outfile1, outfile2

def kraken_func(path, infile1, infile2, threads, common_name, path_kraken):
    ''' Function that runs Kraken on two raw reads fastq files, one forward (1, right) and one reverse(2, left), 
    in order to assign taxonomic labels to the sequences'''
    os.chdir(path)

    log_parse(f'Kraken started with {infile1} and {infile2} as input with {threads} threads available \n', path)
    kraken_output = f'out_kraken_{common_name}.out'
    kraken_report = f'report_kraken_{common_name}.report'

    krakeninput = f'kraken2 --db {path_kraken} --threads {threads} --output {kraken_output} --report {kraken_report} --paired {infile1} {infile2}'
    
    os.system(krakeninput)# I dont know if this generates outpu, but in that case I should be parsed into logfile like below
    #os.system(f'{krakeninput} >> {logname}') 

    log_parse(f'Kraken run finished. Two output files returned:\n', path)
    log_parse(f'{kraken_output} \n{kraken_report}', path)
    return kraken_output, kraken_report

def reads_for_coverage(path, fastq_file, wanted_coverage, genome_size):
    '''Function that checks whether the requested coverage can be reached with the input
    files, returning the maximum coverage if this is not the case.'''
    os.chdir(path)

    log_parse(f'Running: reads_for_coverage')
    log_parse(f'Checking if coverage can be achieved \n\n')

    bases_needed = int(wanted_coverage*genome_size/2)
    
    log_parse(f'To achieve {wanted_coverage} X, {bases_needed} bases are needed from each fastq-file\n')
    log_parse(f'Checking if wanted coverage can be achieved...')
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
                log_parse(f'Coverage can be reached! It amounts to {read_counter} reads from fastq_1 which is {total_bases} bases\n\n')
                coverage = wanted_coverage
                break

            row_counter = row_counter%4 + 1 # makes the counter loop between 1 and 4


    # Give log output if the coverage CANNOT be achieved, and estimate new coverage
    if total_bases < bases_needed:
        log_parse(f'There are not enough bases to achieve {wanted_coverage} X coverage.\n"')
        available_coverage = int((2*total_bases)/genome_size)
        log_parse( f'Using an estimated coverage of {available_coverage} X instead which amounts to {read_counter} reads and {total_bases} bases from fastq_1\n\n')
        coverage = available_coverage

    reads_needed = read_counter
    
    log_parse( f'Function finished.\nOutputs: coverage {coverage}, reads needed {reads_needed}\n\n')

    return coverage, reads_needed

def shorten_fastq(path, fastq1_file, fastq2_file, reads_needed, common_name):
    '''Function that shortens the fastq files to only be long enough to reach 
    the requested coverage.'''
    os.chdir(path)

    log_parse( f'shorten_fastq started to shorten {fastq1_file} and {fastq2_file} to only match wanted coverage.\n\n', path)

    lines_needed = reads_needed*4
    newname1 = f'X_{common_name}_1.fastq.gz'
    newname2 = f'X_{common_name}_2.fastq.gz'
    
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

    log_parse( f'Shortening complete.\nOutputs: {newname1}, {newname2}.\n\n', path)

    return newname1, newname2

def spades_func(path, file1, file2, path_spades, common_name, finalpath, threads): # threads, RAM
    '''Function that runs SPAdes to assemble contigs from short reads.'''
    os.chdir(path)

    log_parse('SPAdes started\n', path)

    # To make sure X_spades output is in the correct output directory. 
    # Pilon output will also be added here
    assembly_path = f'{finalpath}/{common_name}_assembly'

    # commandline = '#SBATCH -p node -n 1 \n'
    commandline = f'python {path_spades}/spades.py --careful -o {assembly_path} --pe1-1 {file1} --pe1-2 {file2} -t {threads}'
    os.system(commandline)
    #"spades.py --careful -o $filename1_short\_$wanted_coverage\X_spades --pe1-1 $read1_output --pe1-2 $read2_output -t $threads_available -m $RAM_available"

    # rename from contigs.fasta to fasta to work with pilon
    os.system(f'cp {assembly_path}/contigs.fasta {assembly_path}/{common_name}.fasta')
    log_parse( f'"contigs.fasta"-file copied and renamed to be called "{common_name}.fasta"', path)

    log_parse('SPAdes finished.\n', path)
    log_parse(f'All output files can be found here: {assembly_path}\n\n', path)

    return assembly_path

def pilon_func(fastafile, fasta1, fasta2, common_name, threads, assembly_path):
    '''Function that runs Pilon on contigs-file from SPAdes to 
    polish and assemble further.'''
    
    current = os.getcwd()
    
    os.chdir(assembly_path)
    
    log_parse('Pilon started', current)
    log_parse(f'Input files: {fastafile}, {fasta1}, {fasta2}', current)

    bowtie_build = f'bowtie2-build -f --threads {threads} --quiet {fastafile} {common_name}'
    os.system(bowtie_build)

    # inputs the two shortened fasta-files, if available
    bowtie = f'bowtie2 -x {common_name} -1 {fasta1} -2 {fasta2} -S {common_name}.sam --phred33 --very-sensitive-local --no-unal -p {threads}'
    os.system(bowtie)

    os.system(f'samtools view -bh {common_name}.sam > {common_name}.bam')
    os.system(f'samtools sort {common_name}.bam -o {common_name}.sorted.bam')
    os.system(f'samtools index {common_name}.sorted.bam')

    time = currenttime()+'\n'
    log_parse( f'Pilon 1.24 started at {time}', current)
    
    os.system(f'pilon --genome {common_name}.fasta --frags {common_name}.sorted.bam --output {common_name}.pilon --changes --threads {threads}')
    
    #time = currenttime()+'\n'
    #log_parse(f'Pilon finished at {time}\n')

    log_parse(f'Pilon finished\n', current) #removed at time. keep? 
    
    log_parse( f'Corrected fasta file created: {common_name}.pilon.fasta', current)

    os.chdir(current)

    return 

def info(path, spades_assembly):
    '''Function that uses an assembly-file from SPAdes of Pilon 
    and returns the metrics of that assembly.'''

    # Output som pandas table for att satta ihop alla strains till en sammanstalld csv-fil, 
    # och varje strain till var sin csv-fil
    os.chdir(path)

    log_parse( 'Looking at the metrics of assembly_fasta\n', path)

    number_of_contigs, bases_in_contig, total_bases = 0, 0, 0
    contig_lengths = []
    non_base, number_AT, number_GC = 0, 0, 0
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
    
    log_parse( f'The number of contigs: {number_of_contigs}, the total number of bases: {total_bases}\n')

    contig_lengths.sort()
    longest = contig_lengths[-1]
    log_parse(  f'Longest contig: {longest}\n')
    log_parse(  f'Contigs longer than 1 kb: {contigs_over_1000}')


    # N50
    temp = 0
    for length in contig_lengths:
        temp += length
        N_50 = length
        if temp >= (total_bases/2):
            break
    
    log_parse( f'N50: {N_50}\n')

    # GC-content
    GC = round(number_GC*100/(number_GC + number_AT),2)
    log_parse( f'The GC-content of the sequence is {GC}%. {non_base} non-base characters were excluded from GC-calculation\n')

    log_parse( f'-----------------------Metrics finished-----------------------')

    # PLACE ALL INFO IN PANDAS TABLE
    data = {'Total nr bases': total_bases, 'Nr contigs': number_of_contigs, 'Longest contig': longest, 
    'Nr contigs > 1kb': contigs_over_1000, 'N50':N_50, 'GC-content': GC}

    info_df = pd.DataFrame(data=data, index=[0])

    return info_df

def regular(path, infile1, infile2, run_fastp, kraken, ariba, db_ariba, run_spades, wanted_coverage, genome_size, pilon, threads):
    '''Function that runs the regular pipeline. This function is called from the parallelize
    function in the case of calling the pipeline with a directory of multiple reads files.
    Requires an output path, a forward file (1), a reverse file (2) as well as other predetermined 
    parameters'''

    time = currenttime()
    date = str(datetime.date(datetime.now()))

    path_tools = '/proj/uppmax2022-2-14/private/campy_pipeline/assembly/verktyg'
    path_spades = path_tools + '/SPAdes-3.15.4-Linux/bin'
    path_kraken = path_tools + '/minikraken2_v1_8GB'

    os.system(f'cp {infile1} {infile2} {path}')
    os.chdir(path)

# if path for infiles has been sent in, then shorten the names. Otherwise there will be no change.
    infile1 = infile1.split('/')[-1]
    infile2 = infile2.split('/')[-1]

    common_name = shortname(infile1)

# Create log file
    global logname
    logname = 'logfile.txt'
    os.chdir(path)
    create_log(path, time, date, logname)
    print(f'Pipeline started, please refer to logfile "{logname}" for updates.')

# Ariba 
    if ariba:
        header= '\n'+'='*15 +'ARIBA'+ '='*15 +'\n'
        log_parse(header, path)
        ariba_fun(path, infile1,infile2, db_ariba)
        #os.system("ariba summary out_sum out.run.*/report.tsv") #change from v5
        os.system("ariba summary out.sum out.run.*/report.tsv")

# Fastp
    if run_fastp:
        header= '\n'+'='*15 +'FASTP'+ '='*15 +'\n'
        log_parse(header, path)
        outfile1_trim, outfile2_trim = fastp_func(path, infile1, infile2, common_name)

        infile1 = outfile1_trim
        infile2 = outfile2_trim

# Kraken
    if kraken:
        header= '\n'+'='*15 +'KRAKEN'+ '='*15 +'\n'
        log_parse(header, path)
        kraken_output, kraken_report = kraken_func(path, infile1, infile2, threads, common_name, path_kraken)

# Number of reads to match the wanted coverage
    if run_spades:
        header= '\n'+'='*15 +'READS FOR COVERAGE, SPADES'+ '='*15 +'\n'
        log_parse(header, path)
        coverage, reads_needed = reads_for_coverage(path, infile1, wanted_coverage, genome_size)
    else:
        coverage = 0

# Shortening fastq-files if the coverage can be reached with less
    if coverage > wanted_coverage:
        outfile1_shorten, outfile2_shorten = shorten_fastq(path, infile1, infile2, reads_needed, common_name)        
        infile1 = outfile1_shorten
        infile2 = outfile2_shorten
        os.system(f'mv {outfile1_shorten} {outfile2_shorten} {path}')
        log_parse(f'Shortened fastq files from shorten_fastq function moved to directory\n\n', path)

# Spades
    if run_spades:
        header= '\n'+'='*15 +'SPADES'+ '='*15 +'\n'
        log_parse(header, path)
        assembly_path = spades_func(path, infile1, infile2, path_spades, common_name, path, threads)

# Pilon
    if pilon:
        header= '\n'+'='*15 +'PILON'+ '='*15 +'\n'
        log_parse(header, path)
        fastafile = f'{assembly_path}/{common_name}.fasta'
        pilon_func(fastafile, infile1, infile2, common_name, threads, assembly_path)
        
        # input file found here: assembly_path/SRR18825428.fasta

# Info/metrics
    if run_spades:
        header= '\n'+'='*15 +'INFO/METRICS, SPADES'+ '='*15 +'\n'
        log_parse(header, path)

        from_spades = f'{assembly_path}/{common_name}.fasta'
        
        info_df = info(path, from_spades)
        info_df.to_csv(header = True, path_or_buf = f'{path}/{common_name}_info.csv')
        
        # If we have multiple info_df then use pd.concat([info_df1, info_df2], axis=0) to stack the 2nd below the 1st.
        # This is useful when running in parallel.
        
        # Save info_df INSTEAD KEEP AS DF AND CONCAT WITH KRAKEN AND ALIGNMENT
        info_df.to_csv(os.PathLike(f'{path}/{common_name}_metrics'))
        
        # 1. change ariba out.db.tsv and kraken report to csv
        # 2. concatenate ariba overview, kraken and info to one csv-file in the variable results_csv

        # os.system(mv results_csv finalpath)

def map_func(dir, f):
    '''Function to map regular to files and directory when running in parallel'''
    return regular(dir, f[0], f[1], run_fastp, kraken, ariba, db_ariba, run_spades, wanted_coverage, genome_size, pilon, threads)

def parallelize(finalpath, file_directory):
    '''Function that takes a directory of forward and reverse files to run the 
    pipeline with in parallel. Also takes a final path to the collective directory'''
    
    global base_dir
    base_dir = os.getcwd()
    os.chdir(file_directory)
    os.system(f"ls *.gz > input.txt")
    # go back
    os.chdir(base_dir)

    dirlist = []
    files = []
    com_names=[]
    with open(f'{file_directory}/input.txt', 'r') as inp:
        linelist = inp.readlines()
        for i in range(0, len(linelist), 2):
            common_name = shortname(linelist[i])
            com_names.append(common_name) # EDITED: for use in sum_info file
            path = f'{finalpath}/{common_name}'
            os.mkdir(path)
            dirlist.append(path)
            f1 = linelist[i].strip('\n')
            f2 = linelist[i+1].strip('\n')
            files.append((f'{file_directory}/{f1}', f'{file_directory}/{f2}'))
    
    with future.ThreadPoolExecutor() as ex:
        ex.map(map_func, dirlist, files)

    os.system(f'cd {finalpath}') # change back to finalpath ??? yes <3
 
    # Creating combined info-files for parallellized genomes, currently names are last but works. OK?
    finalname="sum_info" #change?
    infopath= os.getcwd() # correct? where are we standing?
    all_filenames = [i for i in glob.glob(f'*/info.csv')]  
    combined_csv = pd.concat([pd.read_csv(f) for f in all_filenames ], axis=0) 
    combined_csv["Genome Name"] = com_names # EDITED: from appending names in loop above
    combined_csv.to_csv( f'{infopath}/{finalname}.csv', index=False, encoding='utf-8-sig')
    

def main():
    """
    path/to/file1 path/to/file2 here nopar notrim nokraken ariba [db1, db2] 0 size nopilon thr ram
    """
    global infile1, infile2, new_location, run_fastp, kraken, ariba, db_ariba, wanted_coverage, genome_size, pilon, threads, run_spades
    infile1 = sys.argv[1] # 
    infile2 = sys.argv[2]
    new_location = sys.argv[3] == 'there' # will ask for directory location if True
    run_fastp = sys.argv[4] == 'trim' # will run fastp if True
    kraken = sys.argv[5] == 'kraken'
    ariba = sys.argv[6] == 'ariba'
    db_ariba = sys.argv[7][1:-1].strip(" ").split(',')
    wanted_coverage = int(sys.argv[8]) # if wanted coverage == 0, then don't run spades
    genome_size = int(sys.argv[9])
    pilon = sys.argv[10] == 'pilon'
    threads = sys.argv[11]
    # RAM = sys.argv[12] # this has not been implemented

    run_spades = wanted_coverage != 0

    if pilon and run_spades == False: # Since pilon requires spades output, this 
        pilon = False
        pilon_lines = 'Pilon not run since SPAdes was not run (!)\n\n'

# Let's start this pipeline!
    time = currenttime()
    date = str(datetime.date(datetime.now()))
    
# make directory for output
    finalpath = directory(date, time, new_location)

    if os.path.isdir(infile1):
        parallelize(finalpath, infile1)
    else:
        regular(finalpath, infile1, infile2, run_fastp, kraken, ariba, db_ariba, run_spades, wanted_coverage, genome_size, pilon, threads)


if __name__ == '__main__':
    main()  