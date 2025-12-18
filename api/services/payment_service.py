"""
Payment Service
Handles Stripe payments and subscription management
"""

import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import stripe


class PaymentService:
    """Service for managing payments and subscriptions"""

    def __init__(self, db):
        """
        Initialize payment service

        Args:
            db: Firestore database client
        """
        self.db = db
        stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
        self.price_single = os.environ.get('STRIPE_PRICE_SINGLE', 'price_single_class')
        self.price_bundle = os.environ.get('STRIPE_PRICE_BUNDLE', 'price_bundle')

        # Free access users (for testing)
        free_users_str = os.environ.get('FREE_ACCESS_USERS', '')
        self.free_access_users = [u.strip() for u in free_users_str.split(',') if u.strip()]

    def has_active_subscription(self, user_id: str) -> bool:
        """
        Check if user has an active subscription

        Args:
            user_id: Firebase user ID

        Returns:
            True if user has active subscription
        """
        # Check if user is in free access list
        user_doc = self.db.collection('users').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            if user_data.get('email') in self.free_access_users:
                return True

        # Check subscription status
        sub_doc = self.db.collection('subscriptions').document(user_id).get()
        if not sub_doc.exists:
            return False

        sub_data = sub_doc.to_dict()
        status = sub_data.get('status')

        if status in ['active', 'trialing']:
            return True

        # Check if within grace period (7 days after expiration)
        current_period_end = sub_data.get('current_period_end')
        if current_period_end:
            end_date = datetime.fromisoformat(current_period_end.replace('Z', '+00:00'))
            grace_end = end_date + timedelta(days=7)
            if datetime.now(end_date.tzinfo) < grace_end:
                return True

        return False

    def get_subscription(self, user_id: str) -> Dict:
        """
        Get subscription details for a user

        Args:
            user_id: Firebase user ID

        Returns:
            Subscription details
        """
        # Check for free access
        user_doc = self.db.collection('users').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            if user_data.get('email') in self.free_access_users:
                return {
                    'status': 'active',
                    'plan': 'free',
                    'plan_name': 'Free Access',
                    'is_free': True
                }

        # Get subscription from Firestore
        sub_doc = self.db.collection('subscriptions').document(user_id).get()

        if not sub_doc.exists:
            return {
                'status': 'none',
                'plan': None,
                'plan_name': 'No subscription',
                'is_free': False
            }

        sub_data = sub_doc.to_dict()

        return {
            'status': sub_data.get('status', 'unknown'),
            'plan': sub_data.get('plan', 'single'),
            'plan_name': self._get_plan_name(sub_data.get('plan')),
            'current_period_end': sub_data.get('current_period_end'),
            'cancel_at_period_end': sub_data.get('cancel_at_period_end', False),
            'stripe_subscription_id': sub_data.get('stripe_subscription_id'),
            'is_free': False
        }

    def _get_plan_name(self, plan: str) -> str:
        """Get human-readable plan name"""
        names = {
            'single': 'Single Class',
            'bundle': 'Multi-Class Bundle',
            'free': 'Free Access'
        }
        return names.get(plan, 'Unknown Plan')

    def create_checkout_session(self, user_id: str, price_id: str,
                                 success_url: str, cancel_url: str) -> str:
        """
        Create a Stripe checkout session

        Args:
            user_id: Firebase user ID
            price_id: Stripe price ID
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel

        Returns:
            Checkout session URL
        """
        # Get user email
        user_doc = self.db.collection('users').document(user_id).get()
        email = None
        if user_doc.exists:
            email = user_doc.to_dict().get('email')

        # Check for existing Stripe customer
        customer_id = None
        sub_doc = self.db.collection('subscriptions').document(user_id).get()
        if sub_doc.exists:
            customer_id = sub_doc.to_dict().get('stripe_customer_id')

        # Create checkout session
        session_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': price_id,
                'quantity': 1
            }],
            'mode': 'subscription',
            'success_url': success_url,
            'cancel_url': cancel_url,
            'metadata': {
                'user_id': user_id
            }
        }

        if customer_id:
            session_params['customer'] = customer_id
        elif email:
            session_params['customer_email'] = email

        # Allow subscription updates
        session_params['subscription_data'] = {
            'metadata': {
                'user_id': user_id
            }
        }

        session = stripe.checkout.Session.create(**session_params)

        return session.url

    def handle_checkout_completed(self, session: Dict):
        """
        Handle successful checkout

        Args:
            session: Stripe checkout session object
        """
        user_id = session.get('metadata', {}).get('user_id')
        if not user_id:
            print("No user_id in checkout session metadata")
            return

        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        # Get subscription details from Stripe
        subscription = stripe.Subscription.retrieve(subscription_id)

        # Determine plan from price
        plan = 'single'
        if subscription.get('items', {}).get('data'):
            price_id = subscription['items']['data'][0]['price']['id']
            if price_id == self.price_bundle:
                plan = 'bundle'

        # Update subscription in Firestore
        self.db.collection('subscriptions').document(user_id).set({
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': subscription_id,
            'status': subscription.get('status', 'active'),
            'plan': plan,
            'current_period_start': datetime.fromtimestamp(
                subscription.get('current_period_start', 0)
            ).isoformat(),
            'current_period_end': datetime.fromtimestamp(
                subscription.get('current_period_end', 0)
            ).isoformat(),
            'cancel_at_period_end': subscription.get('cancel_at_period_end', False),
            'updated_at': datetime.now().isoformat()
        })

        # Log payment
        self.db.collection('payments').document(user_id).collection('history').add({
            'type': 'subscription_created',
            'amount': session.get('amount_total', 0) / 100,
            'currency': session.get('currency', 'usd'),
            'stripe_session_id': session.get('id'),
            'created_at': datetime.now().isoformat()
        })

    def handle_subscription_updated(self, subscription: Dict):
        """
        Handle subscription update

        Args:
            subscription: Stripe subscription object
        """
        user_id = subscription.get('metadata', {}).get('user_id')
        if not user_id:
            # Try to find user by customer ID
            customer_id = subscription.get('customer')
            users = self.db.collection('subscriptions').where(
                'stripe_customer_id', '==', customer_id
            ).limit(1).stream()

            for user in users:
                user_id = user.id
                break

        if not user_id:
            print("Could not find user for subscription update")
            return

        # Update subscription in Firestore
        self.db.collection('subscriptions').document(user_id).update({
            'status': subscription.get('status', 'active'),
            'current_period_start': datetime.fromtimestamp(
                subscription.get('current_period_start', 0)
            ).isoformat(),
            'current_period_end': datetime.fromtimestamp(
                subscription.get('current_period_end', 0)
            ).isoformat(),
            'cancel_at_period_end': subscription.get('cancel_at_period_end', False),
            'updated_at': datetime.now().isoformat()
        })

    def handle_subscription_cancelled(self, subscription: Dict):
        """
        Handle subscription cancellation

        Args:
            subscription: Stripe subscription object
        """
        user_id = subscription.get('metadata', {}).get('user_id')
        if not user_id:
            customer_id = subscription.get('customer')
            users = self.db.collection('subscriptions').where(
                'stripe_customer_id', '==', customer_id
            ).limit(1).stream()

            for user in users:
                user_id = user.id
                break

        if not user_id:
            print("Could not find user for subscription cancellation")
            return

        # Update subscription status
        self.db.collection('subscriptions').document(user_id).update({
            'status': 'cancelled',
            'cancelled_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        })

    def cancel_subscription(self, user_id: str) -> bool:
        """
        Cancel a user's subscription

        Args:
            user_id: Firebase user ID

        Returns:
            True if successful
        """
        sub_doc = self.db.collection('subscriptions').document(user_id).get()
        if not sub_doc.exists:
            return False

        sub_data = sub_doc.to_dict()
        subscription_id = sub_data.get('stripe_subscription_id')

        if not subscription_id:
            return False

        try:
            # Cancel at period end (user keeps access until then)
            stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )

            # Update Firestore
            self.db.collection('subscriptions').document(user_id).update({
                'cancel_at_period_end': True,
                'updated_at': datetime.now().isoformat()
            })

            return True

        except Exception as e:
            print(f"Error cancelling subscription: {str(e)}")
            return False

    def get_payment_history(self, user_id: str, limit: int = 20) -> List[Dict]:
        """
        Get payment history for a user

        Args:
            user_id: Firebase user ID
            limit: Maximum number of records

        Returns:
            List of payment records
        """
        history_ref = self.db.collection('payments').document(user_id).collection('history')
        docs = history_ref.order_by('created_at', direction='DESCENDING').limit(limit).stream()

        history = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            history.append(data)

        return history

    def create_customer_portal_session(self, user_id: str, return_url: str) -> str:
        """
        Create a Stripe customer portal session

        Args:
            user_id: Firebase user ID
            return_url: URL to return to

        Returns:
            Portal session URL
        """
        sub_doc = self.db.collection('subscriptions').document(user_id).get()
        if not sub_doc.exists:
            raise ValueError("No subscription found")

        customer_id = sub_doc.to_dict().get('stripe_customer_id')
        if not customer_id:
            raise ValueError("No Stripe customer found")

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url
        )

        return session.url
