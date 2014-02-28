@shard_2
Feature: CMS.Pages
    As a course author, I want to be able to add pages

    Scenario: Users can add pages
        Given I have opened a new course in Studio
        And I go to the pages page
        Then I should not see any pages
        When I add a new page
        Then I should see a page named "Empty"

    Scenario: Users can delete pages
        Given I have created a page
        When I "delete" the page
        Then I am shown a prompt
        When I confirm the prompt
        Then I should not see any pages

    # Safari won't update the name properly
    @skip_safari
    Scenario: Users can edit pages
        Given I have created a page
        When I "edit" the page
        And I change the name to "New"
        Then I should see a page named "New"

    # Safari won't update the name properly
    @skip_safari
    Scenario: Users can reorder pages
        Given I have created two different pages
        When I reorder the tabs
        Then the tabs are in the reverse order
        And I reload the page
        Then the tabs are in the reverse order
