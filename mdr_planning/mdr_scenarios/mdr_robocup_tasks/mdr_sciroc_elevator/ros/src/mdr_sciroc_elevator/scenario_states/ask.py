import rospy
import actionlib
from rasa_nlu.model import Interpreter

from mas_execution_manager.scenario_state_base import ScenarioStateBase
from mdr_listen_action.msg import ListenAction, ListenGoal
from speech_matching.speech_matching import SpeechMatching
from mas_tools.ros_utils import get_package_path

class AskFloor(ScenarioStateBase):
    def __init__(self, save_sm_state=False, **kwargs):
        ScenarioStateBase.__init__(self, 'listening',
                                   save_sm_state=save_sm_state,
                                   input_keys=[],
                                   output_keys=['target_entity'],
                                   outcomes=['succeeded', 'failed',
                                             'failed_after_retrying'])

        self.sm_id = kwargs.get('sm_id', '')
        self.state_name = kwargs.get('state_name', '')
        self.number_of_retries = kwargs.get('number_of_retries', 0)
        self.timeout = kwargs.get('timeout', 25)
        self.threshold = kwargs.get('threshold', 0.68)
        self.floor_number = kwargs.get('floor_number', '')

        # Load the rasa model
        model_directory = get_package_path('rasa_nlu_models', 'common',
                                           'where_is_this', 'nlu')
        self.interpreter = Interpreter.load(model_directory)

        # wait for listen action server
        self.listen_client = actionlib.SimpleActionClient("listen_server", ListenAction)
        listen_wait_result = self.listen_client.wait_for_server(timeout=rospy.Duration(self.timeout))
        if not listen_wait_result:
            raise RuntimeError('failed to wait for "listen_server" action')

        # Speech Matcher
        self.speech_matcher = SpeechMatching()

    def execute(self, userdata):
        # Setup the listen goal
        goal = ListenGoal()

        if not self.number_of_retries == 0:
            if self.state_name == "ASK_HELP":
                self.say('Can you please press number ' + self.floor_number + '?')
            elif self.state_name == "ASK_FLOOR":
                self.say('Are we in floor number ' + self.floor_number + '?')
            rospy.sleep(1)
        # Ask again if not understood the first time
        elif self.number_of_retries < 3:
            self.say("Sorry, I didn't understand you. Could you repeat that please?")
            rospy.sleep(3)

        # Listen for speech
        self.listen_client.send_goal(goal)
        self.listen_client.wait_for_result(rospy.Duration.from_sec(int(self.timeout)))
        listen_result = self.listen_client.get_result()

        if listen_result is None:
            rospy.logerr("Could not get input, listen action returned None")
            return "failed"
        rospy.loginfo("Understood: {}".format(listen_result.message))

        # Try to get the intent
        rasa_result = self.interpreter.parse(listen_result.message)
        speech_intent = rasa_result["intent"]

        # Check if the intention and the confidence are right
        if speech_intent["name"] != "affirmation":
            rospy.logerr(' -> Intent is not affirmation')

            if speech_intent["confidence"] < self.threshold:
                rospy.logerr(' -> Confidence for the intent is too low: {}'.format(speech_intent["confidence"]))

            if len(rasa_result["entities"]) < 1:
                rospy.logerr(' -> Could not extract object entity')
            return "failed"
        else:
            # Focus on one entity first
            if len(rasa_result["entities"]) == 0:
                return "failed"
            else:

                rospy.loginfo('Successfully got affirmation!')
                return 'succeeded'

        # Conversation has exceeded the maximum number of retries at this point
        rospy.loginfo('Could not understand you, aborting operation. ')
        self.say('Sorry, I definitively cannot understand you! Aborting operation!')

        return 'failed_after_retrying'
