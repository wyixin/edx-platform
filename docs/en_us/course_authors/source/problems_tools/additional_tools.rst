.. _Additional Tools:


#############################
Additional Tools
#############################

*************************
Additional Tools Overview
*************************

Individual course teams frequently create tools and problem types that don't have templates in Studio. We want to make these tools available to all our course teams. 

Below, we provide you with all the files and code that you need to create the following tools and problem types.

* :ref:`Chemical Equation`
* :ref:`Conditional Module`
* :ref:`Gene Explorer`
* :ref:`Interactive Periodic Table`
* :ref:`Molecule Editor`
* :ref:`Multiple Choice and Numerical Input`
* :ref:`Polls`
* :ref:`Protein Builder`


.. _Chemical Equation:

**************************
Chemical Equation Problem
**************************

The chemical equation problem type allows the student to enter text that represents a chemical equation into a text box. The LMS converts that text into a chemical equation below the text box. The grader evaluates the student's response by using a Python script that you create and embed in the problem.

.. image:: ../Images/ChemicalEquationExample.png
 :alt: Image of a chemical equation response problem

====================================
Create the Chemical Equation Problem
====================================

Chemical equation problems use MathJax to create formulas. For more information about using MathJax in Studio, see :ref:`MathJax in Studio`.

To create the above chemical equation problem:

#. In the unit where you want to create the problem, click **Problem** under **Add New Component**, and then click the **Advanced** tab.
#. Click **Blank Advanced Problem**.
#. In the component that appears, click **Edit**.
#. In the component editor, paste the code from below.
#. Click **Save**.


Sample Chemical Equation Problem Code
-------------------------------------

.. code-block:: xml

  <problem>
    <startouttext/>
    <p>Some problems may ask for a particular chemical equation. Practice by writing out the following reaction in the box below.</p>
    
  \( \text{H}_2\text{SO}_4 \longrightarrow \text { H}^+ + \text{ HSO}_4^-\)

    <customresponse>
      <chemicalequationinput size="50" label="Enter the chemical equation"/>
      <answer type="loncapa/python">

  if chemcalc.chemical_equations_equal(submission[0], 'H2SO4 -> H^+ + HSO4^-'):
      correct = ['correct']
  else:
      correct = ['incorrect']

      </answer>
    </customresponse>
    <p>Some tips:</p>
    <ul>
    <li>Use real element symbols.</li>
    <li>Create subscripts by using plain text.</li>
    <li>Create superscripts by using a caret (^).</li>
    <li>Create the reaction arrow (\(\longrightarrow\)) by using "->".</li>
    </ul>

    <endouttext/>
  
   <solution>
   <div class="detailed-solution">
   <p>Solution</p>
   <p>To create this equation, enter the following:</p>
     <p>H2SO4 -> H^+ + HSO4^-</p>
   </div>
   </solution>
  </problem>

.. _Conditional Module:

******************
Conditional Module
******************

==================
Format description
==================

The main tag of Conditional module input is:

.. code-block:: xml

    <conditional> ... </conditional>

``conditional`` can include any number of any xmodule tags (``html``, ``video``, ``poll``, etc.) or ``show`` tags.

conditional tag
---------------

The main container for a single instance of Conditional module. The following attributes can
be specified for this tag::

    sources - location id of required modules, separated by ';'
    [message | ""] - message for case, where one or more are not passed. Here you can use variable {link}, which generate link to required module.

    [submitted] - map to `is_submitted` module method.
    (pressing RESET button makes this function to return False.)

    [correct] - map to `is_correct` module method
    [attempted] - map to `is_attempted` module method
    [poll_answer] - map to `poll_answer` module attribute
    [voted] - map to `voted` module attribute

show tag
--------

Symlink to some set of xmodules. The following attributes can
be specified for this tag::

    sources - location id of modules, separated by ';'

=======
Example
=======

Examples of conditional depends on poll
-------------------------------------------

.. code-block:: xml

    <conditional sources="i4x://MITx/0.000x/poll_question/first_real_poll_seq_with_reset" poll_answer="man"
    message="{link} must be answered for this to become visible.">
        <html>
            <h2>You see this, cause your vote value for "First question" was "man"</h2>
        </html>
    </conditional>

Examples of conditional depends on poll (use <show> tag)
--------------------------------------------------------

.. code-block:: xml

    <conditional sources="i4x://MITx/0.000x/poll_question/first_real_poll_seq_with_reset" poll_answer="man"
    message="{link} must be answered for this to become visible.">
        <html>
            <show sources="i4x://MITx/0.000x/problem/test_1; i4x://MITx/0.000x/Video/Avi_resources; i4x://MITx/0.000x/problem/test_1"/>
        </html>
    </conditional>

Examples of conditional depends on problem
-------------------------------------------

.. code-block:: xml

    <conditional sources="i4x://MITx/0.000x/problem/Conditional:lec27_Q1" attempted="True">
        <html display_name="HTML for attempted problem">You see this, cause "lec27_Q1" is attempted.</html>
    </conditional>
    <conditional sources="i4x://MITx/0.000x/problem/Conditional:lec27_Q1" attempted="False">
        <html display_name="HTML for not attempted problem">You see this, cause "lec27_Q1" is not attempted.</html>
    </conditional>


.. _Gene Explorer:

**************************
Gene Explorer
**************************

The Gene Explorer (GeneX), from the biology department at `UMB <http://www.umb.edu/>`_, simulates the transcription, splicing, processing, and translation of a small hypothetical eukaryotic gene. GeneX allows students to make specific mutations in a gene sequence, and it then calculates and displays the effects of the mutations on the mRNA and protein. 

Specifically, the Gene Explorer does the following:

#. Finds the promoter and terminator
#. Reads the DNA sequence to produce the pre-mRNA
#. Finds the splice sites
#. Splices and tails the mRNA
#. Finds the start codon
#. Translates the mRNA

.. image:: ../Images/GeneExplorer.png
  :alt: Image of the Gene Explorer

For more information about the Gene Explorer, see `The Gene Explorer <http://intro.bio.umb.edu/GX/>`_.

=====================
Gene Explorer Code
=====================

::

  <problem>
  <p>Make a single base pair substitution mutation in the gene below that results in a protein that is longer than the protein produced by the original gene. When you are satisfied with your change and its effect, click the <b>SUBMIT</b> button.</p>
  <p>Note that a "single base pair substitution mutation" is when a single base is changed to another base; for example, changing the A at position 80 to a T. Deletions and insertions are not allowed.</p>
  <script type="loncapa/python">
  def genex_grader(expect,ans):
      if ans=="CORRECT": return True
      import json
      ans=json.loads(ans)
      return ans["genex_answer"]=="CORRECT"
  </script>
  <customresponse cfn="genex_grader">
  <editageneinput width="818" height="1000" dna_sequence="TAAGGCTATAACCGAGATTGATGCCTTGTGCGATAAGGTGTGTCCCCCCCCAAAGTGTCGGATGTCGAGTGCGCGTGCAAAAAAAAACAAAGGCGAGGACCTTAAGAAGGTGTGAGGGGGCGCTCGAT" genex_dna_sequence="TAAGGCTATAACCGAGATTGATGCCTTGTGCGATAAGGTGTGTCCCCCCCCAAAGTGTCGGATGTCGAGTGCGCGTGCAAAAAAAAACAAAGGCGAGGACCTTAAGAAGGTGTGAGGGGGCGCTCGAT" genex_problem_number="2"/>
  </customresponse>
  </problem>

In this code:

* **width** and **height** specify the dimensions of the application, in pixels.
* **genex_dna_sequence** is the default DNA sequence that appears when the problem opens.
* **dna_sequence** contains the application's state and the student's answer. This value must be the same as **genex_dna_sequence**. 
* **genex_problem_number** specifies the number of the problem. This number is based on the five gene editor problems in the MITx 7.00x course--for example, if you want this problem to look like the second gene editor problem in the 7.00x course, you would set the **genex_problem_number** value to 2. The number must be 1, 2, 3, 4, or 5.


.. _Interactive Periodic Table:

**************************
Interactive Periodic Table
**************************

You can create an interactive periodic table of the elements to help your students learn about various elements' properties. In the table below, detailed information about each element appears as the student moves the mouse over the element.

.. image:: ../Images/Periodic_Table.png
  :alt: Image of the interactive periodic table

.. _Create the Periodic Table:

==========================
Create the Periodic Table
==========================

To create a periodic table, you need the following files:

* Periodic-Table.js
* Periodic-Table.css
* Periodic-Table-Colors.css
* PeriodicTableHTML.txt

To download all of these files in a .zip archive, click http://files.edx.org/PeriodicTableFiles.zip. 

To create the periodic table, you need an HTML component.

#. Upload all of the files listed above *except PeriodicTable.txt* to the **Files & Uploads** page in your course.
#. In the unit where you want to create the problem, click **HTML** under **Add New Component**, and then click **HTML**.
#. In the component that appears, click **Edit**.
#. In the component editor, switch to the **HTML** tab.
#. Open the PeriodicTable.txt file in any text editor.
#. Copy all of the text in the PeriodicTable.txt file, and paste it into the HTML component editor. (Note that the PeriodicTableHTML.txt file contains over 6000 lines of code. Paste all of this code into the component editor.)
#. Click **Save**.

.. _Molecule Editor:

************************
Molecule Editor
************************

Students can use the molecule editor to learn how to create molecules. The molecule editor allows students to draw molecules that follow the rules for covalent bond formation and formal charge, even if the molecules are chemically impossible, are unstable, or do not exist in living systems. The molecule editor warns students if they try to submit a structure that is chemically impossible.

The molecule editor incorporates two tools: the JSME molecule editor created by Peter Erl and Bruno Bienfait, and JSmol, a JavaScript-based molecular viewer from Jmol. (You don't need to download either of these tools--Studio uses them automatically.) For more information about the JSME molecule editor, see `JSME Molecule Editor <http://peter-ertl.com/jsme/index.html>`_. For more information about JSmol, see `JSmol <http://sourceforge.net/projects/jsmol/>`_.

.. image:: ../Images/Molecule_Editor.png
  :alt: Image of the molecule editor

.. _Create the Molecule Editor:

==========================
Create the Molecule Editor
==========================

To create a molecule editor, you need the following files:

* MoleculeAnswer.png
* MoleculeEditor_HTML.png
* dopamine.mol

To download all of these files in a .zip archive, go to http://files.edx.org/MoleculeEditorFiles.zip.

.. note:: The molecule that appears when the tool starts is a dopamine molecule. To use a different molecule, download the .mol file for that molecule from the `list of molecules <http://www.biotopics.co.uk/jsmol/molecules/>`_ on the `BioTopics <http://www.biotopics.co.uk/>`_ website. Then, upload the .mol file to the **Files & Uploads** page for your course in Studio, and change "dopamine.mol" in the example code to the name of your .mol file.

To create the molecule editor that appears in the image above, you need an HTML component followed by a Problem component.

#. Upload all of the files listed above to the **Files & Uploads** page in your course.
#. Create the HTML component.

  #. In the unit where you want to create the problem, click **HTML** under **Add New Component**, and then click **HTML**.
  #. In the component that appears, click **Edit**.
  #. In the component editor, paste the HTML component code from below.
  #. Make any changes that you want, and then click **Save**.

3. Create the Problem component.

  #. Under the HTML component, click **Problem** under **Add New Component**, and then click **Blank Advanced Problem**.
  #. In the component that appears, click **Edit**.
  #. In the component editor, paste the Problem component code from below.
  #. Click **Save**.

.. _EMC Problem Code:

=====================
Molecule Editor Code
=====================

To create the molecule editor, you need an HTML component and a Problem component.

HTML Component Code
-------------------

.. code-block:: xml

  <h2>Molecule Editor</h2>
  <p>The molecule editor makes creating and visualizing molecules easy. A chemistry professor may have you build and submit a molecule as part of an exercise.</p>
  <div>
  <script type="text/javascript">// <![CDATA[
  function toggle2(showHideDiv, switchTextDiv) {
              var ele = document.getElementById(showHideDiv);
              var text = document.getElementById(switchTextDiv);
              if(ele.style.display == "block") {
                  ele.style.display = "none";
                  text.innerHTML = "+ open";
                  }
              else {
                  ele.style.display = "block";
                  text.innerHTML = "- close";
              }
          }
  // ]]></script>
  </div>
  <div>
  <style type="text/css"></style>
  </div>
  <div id="headerDiv">
  <div id="titleText">Using the Molecule Editor<a id="myHeader" href="javascript:toggle2('myContent','myHeader');">+ open </a></div>
  </div>
  <div id="contentDiv">
  <div id="myContent" style="display: none;">
  <p>In this problem you will edit a molecule using the molecular drawing program shown below:</p>
  <img alt="" src="/static/MoleculeEditor_HTML.png" /></div>
  </div>
  <p>&nbsp;</p>
  <div id="headerDiv">
  <div id="titleText">Are the molecules I've drawn chemically possible?<a id="IntroductionHeader" href="javascript:toggle2('IntroductionContent','IntroductionHeader');">+ open </a></div>
  </div>
  <div id="contentDiv">
  <div id="IntroductionContent" style="display: none;">
  <p>The chemical editor you are using ensures that the structures you draw are correct in one very narrow sense, that they follow the rules for covalent bond formation and formal charge. However, there are many structures that follow these rules that are chemically impossible, unstable, do not exist in living systems, or are beyond the scope of this course. The editor will let you draw them because, in contrast to the rules of formal charge, these properties cannot be easily and reliably predicted from structures.</p>
  <p>If you submit a structure that includes atoms that are not possible or are beyond the scope of this course, the software will warn you specifically about these parts of your structure and you will be allowed to edit your structure and re-submit. Submitting an improper structure will not count as one of your tries. In general, you should try to use only the atoms most commonly cited in this course: C, H, N, O, P, and S. If you want to learn about formal charge, you can play around with other atoms and unusual configurations and look at the structures that result.</p>
  </div>
  </div>
  <div id="ap_listener_added">&nbsp;</div>




Problem Component Code
----------------------
.. code-block:: xml

  <problem>
  <p>The dopamine molecule, as shown, cannot make ionic bonds. Edit the dopamine molecule so it can make ionic bonds.</p>
  <p>When you are ready, click Check. If you need to start over, click Reset.</p>
    <script type="loncapa/python">
  def check1(expect, ans):
      import json
      mol_info = json.loads(ans)["info"]
      return any(res == "Can Make Ionic Bonds" for res in mol_info)
      </script>
    <customresponse cfn="check1">
      <editamoleculeinput file="/static/dopamine.mol">
          </editamoleculeinput>
    </customresponse>
    <solution>
      <img src="/static/MoleculeAnswer.png"/>
    </solution>
  </problem>

**Problem 2**

::

  <problem>
  <p>The dopamine molecule, as shown, cannot make strong hydrogen bonds. Edit the dopamine molecule so that it can make strong hydrogen bonds.</p>
  <script type="loncapa/python">
  def grader_1(expect, ans):
      import json
      mol_info = json.loads(ans)["info"]
      return any(res == "Cannot Make Strong Hydrogen Bonds" for res in mol_info)
  </script>
    <customresponse cfn="grader_1">
      <editamoleculeinput file="/static/dopamine.mol">
      </editamoleculeinput>
    </customresponse>
  </problem>

**Problem 3**

::

  <problem>
  <p>The dopamine molecule has an intermediate hydrophobicity. Edit the dopamine molecule so that it is more hydrophobic.</p>
  <script type="loncapa/python">
  def grader_2(expect, ans):
      import json
      mol_info = json.loads(ans)["info"]

      hydrophobicity_index_str=mol_info[0]
      hydrophobicity_index=float(hydrophobicity_index_str[23:])
      return hydrophobicity_index &gt; .490
  </script>
    <customresponse cfn="grader_2">
      <editamoleculeinput file="/static/dopamine.mol">
      </editamoleculeinput>
  </customresponse>
  </problem>

.. _Multiple Choice and Numerical Input:

*******************************************
Multiple Choice and Numerical Input Problem
*******************************************

You can create a problem that combines a multiple choice and numerical input problems. Students not only select a response from options that you provide, but also provide more specific information, if necessary.

.. image:: ../Images/MultipleChoice_NumericalInput.png
  :alt: Image of a multiple choice and numerical input problem

.. note:: Currently, students can only enter numerals in the text field. Students cannot enter words or mathematical expressions.

.. _Create an MCNA Problem:

====================================================
Create a Multiple Choice and Numerical Input Problem
====================================================

To create a multiple choice and numerical input problem:

#. In the unit where you want to create the problem, click **Problem** under **Add New Component**, and then click the **Advanced** tab.
#. Click **Blank Advanced Problem**.
#. In the component that appears, click **Edit**.
#. In the component editor, paste the code from below.
#. Replace the example problem and response options with your own text.
#. Click **Save**.

.. _MCNA Problem Code:

===================================================
Multiple Choice and Numerical Input Problem Code
===================================================

.. code-block:: xml

  <problem>
  The numerical value of pi, rounded to two decimal points, is 3.24.
  <choicetextresponse>
  <radiotextgroup>
  <choice correct="false">True.</choice>
  <choice correct="true">False. The correct value is <numtolerance_input answer="3.14"/>.</choice>
  </radiotextgroup>
  </choicetextresponse>
  </problem>

.. _Polls:

******
Polls
******

You can run polls in your course so that your students can share opinions on different questions.

.. image:: ../Images/PollExample.png

.. note:: Creating a poll requires you to export your course, edit some of your course's XML files in a text editor, and then re-import your course. We recommend that you create a backup copy of your course before you create the poll. We also recommend that you only edit the files that will contain polls in the text editor if you're very familiar with editing XML. 

===========
Terminology
===========

Sections, subsections, units, and components have different names in the **Course Outline** view and in the list of files that you'll see after you export your course and open the .xml files for editing. The following table lists the names of these elements in the **Course Outline** view and in a list of files.

.. list-table::
   :widths: 15 15
   :header-rows: 0

   * - Course Outline View
     - File List
   * - Section
     - Chapter
   * - Subsection
     - Sequential
   * - Unit
     - Vertical
   * - Component
     - Discussion, HTML, problem, or video

For example, when you want to find a specific section in your course, you'll look in the **Chapter** folder when you open the list of files that your course contains. To find a unit, you'll look in the **Vertical** folder.

.. _Create a Poll:

=============
Create a Poll
=============

#. In the unit where you want to create the poll, create components that contain all the content that you want *except* for the poll. Make a note of the 32-digit unit ID that appears in the **Unit Identifier** field under **Unit Location**.

#. Export your course. For information about how to do this, see :ref:`Exporting and Importing a Course`. Save the .tar.gz file that contains your course in a memorable location so that you can find it easily.

#. Locate the .tar.gz file that contains your course, and then unpack the .tar.gz file so that you can see its contents in a list of folders and files.

   - To do this on a Windows computer, you'll need to download a third-party program. For more information, see `How to Unpack a tar File in Windows <http://www.haskell.org/haskellwiki/How_to_unpack_a_tar_file_in_Windows>`_, `How to Extract a Gz File <http://www.wikihow.com/Extract-a-Gz-File>`_, `The gzip Home Page <http://www.gzip.org/>`_, or the `Windows <http://www.ofzenandcomputing.com/how-to-open-tar-gz-files/#windows>`_ section of the `How to Open .tar.gz Files <http://www.ofzenandcomputing.com/how-to-open-tar-gz-files/>`_ page.

   - For information about how to do this on a Mac, see the `Mac OS X <http://www.ofzenandcomputing.com/how-to-open-tar-gz-files/#mac-os-x>`_ section of the `How to Open .tar.gz Files <http://www.ofzenandcomputing.com/how-to-open-tar-gz-files/>`_ page.

#. In the list of folders and files, open the **Vertical** folder. 

   .. note:: If your unit is not published, open the **Drafts** folder, and then open the **Vertical** folder in the **Drafts** folder.

#. In the **Vertical** folder, locate the .xml file that has the same name as the unit ID that you noted in step 1, and then open the file in a text editor such as Sublime 2. For example, if the unit ID is e461de7fe2b84ebeabe1a97683360d31, you'll open the e461de7fe2b84ebeabe1a97683360d31.xml file.

   The file contains a list of all the components in the unit, together with the URL names of the components. For example, the following file contains an HTML component followed by a Discussion component.

   .. code-block:: xml
     
       <vertical display_name="Test Unit">
        <html url_name="b59c54e2f6fc4cf69ba3a43c49097d0b"/>
        <discussion url_name="8320c3d511484f3b96bdedfd4a44ac8b"/>
       </vertical>

#. Add the following poll code in the location where you want the poll. Change the text of the prompt to the text that you want.

   .. code-block:: xml
      
    <poll_question display_name="Poll Question">
      <p>Text of the prompt</p>
      <answer id="yes">Yes</answer>
      <answer id="no">No</answer>
    </poll_question>

   In the example above, if you wanted your poll to appear between the HTML component and the Discussion component in the unit, your code would resemble the following.

   .. code-block:: xml

     <vertical display_name="Test Unit">
      <html url_name="b59c54e2f6fc4cf69ba3a43c49097d0b"/>
      <poll_question display_name="Poll Question">
        <p>Text of the prompt</p>
        <answer id="yes">Yes</answer>
        <answer id="no">No</answer>
      </poll_question>
      <discussion url_name="8320c3d511484f3b96bdedfd4a44ac8b"/>
     </vertical>

#. After you add the poll code, save and close the .xml file.

#. Re-package your course as a .tar.gz file.

   * For information about how to do this on a Mac, see `How to Create a Tar GZip File from the Command Line <http://osxdaily.com/2012/04/05/create-tar-gzip/>`_.

   * For information about how to do this on a Windows computer, see `How to Make a .tar.gz on Windows <http://stackoverflow.com/questions/12774707/how-to-make-a-tar-gz-on-windows>`_.

#. In Studio, re-import your course. You can now review the poll question and answers that you added in Studio.

.. note::

  * Although polls render correctly in Studio, you cannot edit them in Studio. You will need to follow the export/import process outlined above to make any edits to your polls.
  
  * A .csv file that contains student responses to the problem is not currently available for polls. However, you can obtain the aggregate data directly in the problem.  

==================
Format description
==================

The main tag of Poll module input is:

.. code-block:: xml

    <poll_question> ... </poll_question>

``poll_question`` can include any number of the following tags:
any xml and ``answer`` tag. All inner xml, except for ``answer`` tags, we call "question".

poll_question tag
-----------------

Xmodule for creating poll functionality - voting system. The following attributes can
be specified for this tag::

    name - Name of xmodule.
    [display_name| AUTOGENERATE] - Display name of xmodule. When this attribute is not defined - display name autogenerate with some hash.
    [reset | False] - Can reset/revote many time (value = True/False)


answer tag
----------

Define one of the possible answer for poll module. The following attributes can
be specified for this tag::

    id - unique identifier (using to identify the different answers)

Inner text - Display text for answer choice.

Example
=======

Examples of poll
----------------

.. code-block:: xml

    <poll_question name="second_question" display_name="Second question">
        <h3>Age</h3>
        <p>How old are you?</p>
        <answer id="less18">&lt; 18</answer>
        <answer id="10_25">from 10 to 25</answer>
        <answer id="more25">&gt; 25</answer>
    </poll_question>

Examples of poll with unable reset functionality
------------------------------------------------

.. code-block:: xml

    <poll_question name="first_question_with_reset" display_name="First question with reset"
        reset="True">
        <h3>Your gender</h3>
        <p>You are man or woman?</p>
        <answer id="man">Man</answer>
        <answer id="woman">Woman</answer>
    </poll_question>

.. _Protein Builder:

************************
Protex Protein Builder
************************

The Protex protein builder asks students to create specified protein shapes by stringing together amino acids. In the example below, the goal protein shape is a simple line. 


.. image:: ../Images/ProteinBuilder.png
  :alt: Image of the protein builder

.. _Create the Protein Builder:

==========================
Create the Protein Builder
==========================

To create the protein builder:

#. Under **Add New Component**, click **Problem**, and then click **Blank Advanced Problem**.
#. In the component that appears, click **Edit**.
#. In the component editor, paste the Problem component code from below.
#. Make any changes that you want, and then click **Save**.

.. _Protein Builder Code:

=====================
Protein Builder Code
=====================

.. code-block:: xml

  <problem>
      <p>The protein builder allows you string together the building blocks of proteins, amino acids, and see how that string will form into a structure. You are presented with a goal protein shape, and your task is to try to re-create it. In the example below, the shape that you are asked to form is a simple line.</p> 
     <p>Be sure to click "Fold" to fold your protein before you click "Check".</p>

  <script type="loncapa/python">

  def protex_grader(expect,ans):
    import json
    ans=json.loads(ans)
    if "ERROR" in ans["protex_answer"]:
      raise ValueError("Protex did not understand your answer. Try folding the protein.")
    return ans["protex_answer"]=="CORRECT"

  </script>
 
    <text>
      <customresponse cfn="protex_grader">
        <designprotein2dinput width="855" height="500" target_shape="W;W;W;W;W;W;W"/>
      </customresponse>
    </text>
    <solution>
      <p>
        Many protein sequences, such as the following example, fold to a straight line.You can play around with the protein builder if you're curious.
      </p>
      <ul>
        <li>
            Stick: RRRRRRR
        </li>
      </ul>
    </solution>
  </problem>

In this code:
 
* **width** and **height** specify the dimensions of the application, in pixels.
* **target_shape** lists the amino acids that, combined in the order specified, create the shape you've asked students to create. The list can only include the following letters, which correspond to the one-letter code for each amino acid. (This list appears in the upper-left corner of the protein builder.)

  .. list-table::
     :widths: 15 15 15 15
     :header-rows: 0

     * - A
       - R
       - N
       - D
     * - C
       - Q
       - E
       - G
     * - H
       - I
       - L
       - K
     * - M
       - F
       - P
       - S
     * - T
       - W
       - Y
       - V
