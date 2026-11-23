/**
 * @file
 * The Print button of the Scheduled task report (ScheduledTaskListController::report).
 */
((Drupal, once) => {
  Drupal.behaviors.bibleAdminScheduledTaskReport = {
    attach(context) {
      once('scheduled-task-report-print', '[data-print-report]', context).forEach((button) => {
        button.addEventListener('click', () => window.print());
      });
    },
  };
})(Drupal, once);
