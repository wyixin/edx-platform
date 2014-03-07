@shard_1
Feature: LMS.LTI component
  As a student, I want to view LTI component in LMS.

  #1
  Scenario: LTI component in LMS with no launch_url is not rendered
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with no_launch_url fields:
  | open_in_a_new_page |
  | False              |
  Then I view the LTI and error is shown

  #2
  Scenario: LTI component in LMS with incorrect lti_id is rendered incorrectly
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with incorrect_lti_id fields:
  | open_in_a_new_page |
  | False              |
  Then I view the LTI but incorrect_signature warning is rendered

  #3
  Scenario: LTI component in LMS is rendered incorrectly
  Given the course has incorrect LTI credentials
  And the course has an LTI component with correct fields:
  | open_in_a_new_page |
  | False              |
  Then I view the LTI but incorrect_signature warning is rendered

  #4
  Scenario: LTI component in LMS is correctly rendered in new page
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields
  Then I view the LTI and it is rendered in new page

  #5
  Scenario: LTI component in LMS is correctly rendered in iframe
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields:
  | open_in_a_new_page |
  | False              |
  Then I view the LTI and it is rendered in iframe

  #6
  Scenario: Graded LTI component in LMS is correctly works
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields:
  | open_in_a_new_page | weight | is_graded | has_score |
  | False              | 10     | True      | True      |
  And I submit answer to LTI question
  And I click on the "Progress" tab
  Then I see text "Problem Scores: 5/10"
  And I see graph with total progress "5%"
  Then I click on the "Instructor" tab
  And I click on the "Gradebook" tab
  And I see in the gradebook table that "HW" is "50"
  And I see in the gradebook table that "Total" is "5"

  #7
  Scenario: Graded LTI component in LMS role's masquerading correctly works
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields:
  | open_in_a_new_page | has_score |
  | False              | True      |
  And I view the LTI and it is rendered in iframe
  And I see in iframe that LTI role is Instructor
  And I switch to Student view
  Then I see in iframe that LTI role is Student

  #8
  Scenario: Graded LTI component in LMS is correctly works with beta testers
  Given the course has correct LTI credentials with registered BetaTester
  And the course has an LTI component with correct fields:
  | open_in_a_new_page | weight | is_graded | has_score |
  | False              | 10     | True      | True      |
  And I submit answer to LTI question
  And I click on the "Progress" tab
  Then I see text "Problem Scores: 5/10"
  And I see graph with total progress "5%"

  #9
  Scenario: Graded LTI component in LMS is correctly works with LTI2.0 PUT callback
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields:
  | open_in_a_new_page | weight | is_graded | has_score |
  | False              | 10     | True      | True      |
  And I submit answer to question with LTI 2.0 PUT callback
  And I click on the "Progress" tab
  Then I see text "Problem Scores: 8/10"
  And I see graph with total progress "8%"
  Then I click on the "Instructor" tab
  And I click on the "Gradebook" tab
  And I see in the gradebook table that "HW" is "80"
  And I see in the gradebook table that "Total" is "8"
  And I visit the LTI component
  Then I see progress div with text "Score: 8.00 / 10.0"
  Then I see feedback div with text "awesome"

  #10
  Scenario: Graded LTI component in LMS is correctly works with LTI2.0 PUT delete callback
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields:
  | open_in_a_new_page | weight | is_graded | has_score |
  | False              | 10     | True      | True      |
  And I submit answer to question with LTI 2.0 PUT callback
  And I visit the LTI component
  Then I see progress div with text "Score: 8.00 / 10.0"
  Then I see feedback div with text "awesome"
  And the LTI provider deletes my grade and feedback
  And I visit the LTI component (have to reload)
  Then I do not see progress div
  Then I do not see feedback div
  And I click on the "Progress" tab
  Then I see text "Problem Scores: 0/10"
  And I see graph with total progress "0%"
  Then I click on the "Instructor" tab
  And I click on the "Gradebook" tab
  And I see in the gradebook table that "HW" is "0"
  And I see in the gradebook table that "Total" is "0"

  #11
  Scenario: LTI component that set to hide_launch and open_in_a_new_page shows no button
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields:
  | open_in_a_new_page | hide_launch |
  | False              | True        |
  Then I do not see a launch button
  Then I do see the module title

  #12
  Scenario: LTI component that set to hide_launch and not open_in_a_new_page shows no iframe
  Given the course has correct LTI credentials with registered Instructor
  And the course has an LTI component with correct fields:
  | open_in_a_new_page | hide_launch |
  | True               | True        |
  Then I do not see an provider iframe
  Then I do see the module title
