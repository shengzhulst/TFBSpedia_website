<!-- I want to improve the current frontend, I want to add a new function, which is to constrain the search in certain cell lines/tissue, the table "TFBS_cell_or_tissue" has this information. 

The default setting should not constrain the search, but users can choose to constrain the search in certain cell lines/tissue. add a Dropdown menu on the main page, 

/Users/shitingli/Documents/GitHub/TFBSpedia_django/home/ is where you may need to modify the backend code, and /Users/shitingli/Documents/GitHub/TFBSpedia_django/templates/ is where you may need to modify the frontend code. 

Can you save a file listed all code part you modified? save it here: /Users/shitingli/Documents/GitHub/TFBSpedia_django/instruction/
I need to know which files you modified and what code you added/changed in each file. Please list the file path and the code changes in a clear format. -->



<!-- I want to do some follow up:
The cell line information is already here: /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_tissue_unique_human.csv 
/Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_tissue_unique_mouse.csv

Please use the information in these two files to populate the Dropdown menu for cell lines/tissues. You can read the CSV files(use the relative path please) and extract the unique cell line/tissue names to display in the Dropdown menu.

1) get_all_cell_tissues()(Should be changed)
2) search_by_location() and download_results() and search_by_tf_name() is so slow, I saved a file /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_line_ID_table_human.csv and /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_line_ID_table_mouse.csv, which has the mapping between cell line/tissue names and their corresponding IDs in the database. You can read these files to get the cell line/tissue IDs instead of querying the database every time, which should speed up the search process. -->


<!-- 
I want to do another follow up: -->


<!-- I saved all files with the cell lines IDs in /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_lines_ID_human/ and /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_lines_ID_mouse/, which looks like this for each file.
ID
21462764
21462765
21549649

I want you to modify the search_by_location() and download_results() and search_by_tf_name() functions to read the cell line/tissue IDs from these files based on the user's selection in the Dropdown menu, and use these IDs to constrain the search result in the database. This way, we can avoid querying the database for cell line/tissue information every time, which should significantly speed up the search process.
Also I still want the pagination.


Someother things need to be debug:
1) I also want to include this cell line requirement into the file upload part, can you help add that?
2) It seems like the get_overlap_annotations() has some issues, for example     
 cursor.execute('''
            SELECT h."seqnames", h."start", h."end", h."histone"
            FROM "TFBS_to_histone" th
            JOIN "histone" h ON th."histone_ID" = h."histone_ID"
            WHERE th."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'Histone',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': row[3] if row[3] else ''
            })
seems correct, but the histone information is not showing up in the frontend as the Extra Information column, can you help debug this issue as well?

A small correction is there are annotation called Cookbook_ChIP and Cookbook_GHT_SELEX in the database, it is a typo, it should be Codebook_ChIP and Codebook_GHT_SELEX, Can you just modify the frontend code(html file) to correct this typo? I think it is in the search result page and score introduction page. -->



<!-- I want to do maybe the last follow up:

1) A small correction is there are annotation called Cookbook_GHT_SELEX in the database, it is a typo, it should be Codebook_GHT_SELEX, Can you just modify the frontend code(html file) to correct this typo? I think it is in the search result page and score introduction page.

2) the all count for batch_search_by_tf_name and search_by_tf_name is so slow, you can read the /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_line_TF_count_human.csv and /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_line_TF_count_mouse.csv to get the cell line/tissue IDs counts for search or search TF name, basically, add the count of predicted TFBS and TFBS together for each cell line, the TF_name provided.

3) I want to add another selection feature, TFBS(ChIP-seq) or predicted TFBS (ATAC-seq,DNase-seq) or TFBS/Predicted TFBS(all), in a new Dropdown menu, this selection is big modified for views.py and other files, but the logic is similar to add cell line/tissue selection, you can read the user's selection from the frontend and use it to constrain the search in the database, for example, if the user selects TFBS(ChIP-seq), then you only search in the "TFBS" column in the database.      
since most select region is this


   SELECT DISTINCT
       p."ID",
       p."seqnames",
       p."start",
       p."end"
   FROM "TFBS_position" p
   WHERE EXISTS (
       SELECT 1
       FROM "TFBS_name" n
       WHERE n."ID" = p."ID"
       AND (n."TFBS" = %s OR n."predicted_TFBS" = %s)
   )

so it is easy just to add if else condition for the selection of TFBS/Predicted TFBS in the (n."TFBS" = %s OR n."predicted_TFBS" = %s) part. 

4) put the cell line/tissue selection and TFBS/Predicted TFBS selection into a advanced search setting, which is hidden by default, and users can click to expand it to see these options. -->


I want to let me examin some bugs and improve the design a little.
1) for improve, I found that batch search not match the number of download well. I think it's because the batch search may have duplicate TFBS overlap and the count we calculated are not matched that well. Could you add a notice on the top (small font on top of the file upload place) when move the file upload(really short): Notice: Number of entries may not match the number of download due to TFBS overlap.
2) change the © 2025 TFBSpedia - A Database for Transcription Factor Binding Sites to © 2026 TFBSpedia - A Database for Transcription Factor Binding Sites
3) Read the /Users/shitingli/Documents/GitHub/TFBSpedia_django/staticfiles/documents/cell_line_TF_count_human.csv gonna take long time, it get really large, I am wondering if you have any suggestion on how to speed up the process? Maybe we can read the file once and store the counts in a dictionary in memory when the application starts, so that we can quickly access the counts without reading the file every time. This way, we can significantly reduce the time it takes to get the counts for each cell line and TF name? Is it sound good, or we can save it in pandas or as pickle? Any suggestions?
