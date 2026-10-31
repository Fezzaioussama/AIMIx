import { useState } from 'react';

import type { ClarifyingQuestion, PlanAnswer } from '../../core/api/types';
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from '../pipelines/buttonStyles';
import { Bubble } from './Bubble';
import type { ViewProps } from './messageContext';
import type { QuestionsMessage } from './missionMessages';

const INTRO = 'Before I put your team together, a few questions so I build the right one:';
export const SKIP_SAID = 'Skip the questions and build the team.';

/** How the questions read once they can no longer be answered here. */
const SETTLED: Record<QuestionsMessage['state'], string> = {
  open: '',
  answered: '',
  skipped: 'Skipped: I planned without these answers.',
  closed: '',
};

const CHIP =
  'cursor-pointer rounded-full border border-white/15 px-3 py-1.5 text-sm text-slate-200 transition-colors hover:bg-white/10 has-[:checked]:border-sky-400 has-[:checked]:bg-sky-500/15 has-[:checked]:text-white has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-sky-400';
const OWN_ANSWER =
  'mt-2 w-full rounded-lg border border-white/15 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus-visible:outline-2 focus-visible:outline-sky-400';

/** Each answer with its question, as the person's message says it. */
export function answersInWords(answers: PlanAnswer[]): string {
  return answers.map((item) => `${item.question} — ${item.answer}`).join('\n');
}

interface QuestionFieldProps {
  name: string;
  item: ClarifyingQuestion;
  picked: string;
  written: string;
  onPick: (option: string) => void;
  onWrite: (text: string) => void;
}

/** One question: its suggested answers as chips, and a field for an answer of one's own. */
function QuestionField({ name, item, picked, written, onPick, onWrite }: QuestionFieldProps) {
  const own = written.trim() !== '';
  return (
    <fieldset className="mt-4 first:mt-3">
      <legend className="font-semibold text-slate-50">{item.question}</legend>
      {item.options.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {item.options.map((option) => (
            <label key={option} className={CHIP}>
              <input
                type="radio"
                name={name}
                value={option}
                checked={!own && picked === option}
                onChange={() => onPick(option)}
                className="sr-only"
              />
              {option}
            </label>
          ))}
        </div>
      )}
      <input
        type="text"
        value={written}
        onChange={(event) => onWrite(event.target.value)}
        aria-label={`Your own answer to: ${item.question}`}
        placeholder={item.options.length ? 'Or write your own answer' : 'Your answer'}
        className={OWN_ANSWER}
      />
    </fieldset>
  );
}

type Answer = (answers: PlanAnswer[], said: string) => void;

/** The open questions: pick or write an answer to each, then build, or skip them. */
function QuestionsForm({ message, onAnswer }: { message: QuestionsMessage; onAnswer: Answer }) {
  const blank = message.questions.map(() => '');
  const [picked, setPicked] = useState(blank);
  const [written, setWritten] = useState(blank);
  const set = (list: string[], index: number, value: string) =>
    list.map((current, at) => (at === index ? value : current));

  const answers = message.questions
    .map((item, index) => ({
      question: item.question,
      answer: written[index].trim() || picked[index],
    }))
    .filter((item) => item.answer !== '');

  return (
    <Bubble>
      <p>{INTRO}</p>
      {message.questions.map((item, index) => (
        <QuestionField
          key={item.question}
          name={`${message.id}-${index}`}
          item={item}
          picked={picked[index]}
          written={written[index]}
          onPick={(option) => setPicked((list) => set(list, index, option))}
          onWrite={(text) => setWritten((list) => set(list, index, text))}
        />
      ))}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={answers.length === 0}
          onClick={() => onAnswer(answers, answersInWords(answers))}
          className={PRIMARY_BUTTON}
        >
          Build my team
        </button>
        <button type="button" onClick={() => onAnswer([], SKIP_SAID)} className={SECONDARY_BUTTON}>
          Skip
        </button>
      </div>
      <p className="mt-3 text-xs text-slate-400">You can also answer in the message box.</p>
    </Bubble>
  );
}

/**
 * What the planner asked before building the team. Only the newest open questions can
 * be answered; once answered or skipped they stay in the conversation as plain text.
 */
export function QuestionsMessageView({ message, context }: ViewProps<'questions'>) {
  if (message.id === context.openQuestionsId) {
    const onAnswer: Answer = (answers, said) => context.answerQuestions(message, answers, said);
    return <QuestionsForm message={message} onAnswer={onAnswer} />;
  }
  return (
    <Bubble>
      <p>{INTRO}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {message.questions.map((item) => (
          <li key={item.question}>{item.question}</li>
        ))}
      </ul>
      {SETTLED[message.state] && <p className="mt-2 text-slate-300">{SETTLED[message.state]}</p>}
    </Bubble>
  );
}
