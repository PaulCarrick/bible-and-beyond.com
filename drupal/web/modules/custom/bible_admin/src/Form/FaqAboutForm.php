<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\Component\Utility\Html;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The words about who the site is for, sent to the AI with every FAQ question. In the editor (the owner's rule for
 * multi-line boxes); the AI is sent their plain words, so formatting is not kept.
 */
class FaqAboutForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_faq_about';
  }

  public function buildForm(array $form, FormStateInterface $form_state): array {
    $form['#cache'] = ['max-age' => 0];
    try {
      $about = $this->manager->getFaqQuestionList()['about'];
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $form;
    }
    $form['about'] = GroupEditor::field(
      (string) $this->t('About this site'),
      $about === '' ? '' : '<p>' . Html::escape($about) . '</p>',
      6,
      FALSE,
      (string) $this->t('Who the site is for and how to answer them, such as “This FAQ belongs to Celebrate Recovery at our church; readers are in Christ-centred recovery…”. Sent to the AI with every FAQ question as plain words (up to 2,000 characters), so its answers fit your readers. Changing it gets new answers as visitors open them. Leave it empty to answer as for any Bible study site.'),
    );
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $this->t('Save')];
    $form['actions']['cancel'] = ['#type' => 'link', '#title' => $this->t('Cancel'), '#url' => Url::fromRoute('bible_admin.faq_questions'), '#attributes' => ['class' => ['button']]];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $value = GroupEditor::value($form_state->getValue('about'));
    $text = $value['html'] ?? $value['text'] ?? '';
    // Plain words for the AI: tags become spaces, entities their characters.
    $text = trim(preg_replace('/\s+/u', ' ', Html::decodeEntities(strip_tags(str_replace(['</p>', '<br>', '<br />'], ' ', $text)))));
    try {
      $this->manager->saveFaqAbout($text);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->t('Saved. New answers follow these words as visitors open them.'));
    $form_state->setRedirect('bible_admin.faq_questions');
  }

}
