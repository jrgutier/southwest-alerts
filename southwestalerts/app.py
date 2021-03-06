import logging
import requests
import sys

from southwest import Southwest
import settings


def check_for_price_drops(username, password, email):
    southwest = Southwest(username, password)
    for trip in southwest.get_upcoming_trips()['trips']:
        for flight in trip['flights']:
            passenger = flight['passengers'][0]
            record_locator = flight['recordLocator']
            cancellation_details = southwest.get_cancellation_details(record_locator, passenger['firstName'], passenger['lastName'])
            currency = cancellation_details['currencyType']
            if currency == 'Points':
              itinerary_price = cancellation_details['pointsRefund']['amountPoints'] 
            elif currency == 'Dollars':
              itinerary_price = (cancellation_details['availableFunds']['refundableAmountCents'] + cancellation_details['availableFunds']['nonrefundableAmountCents']) / 100.00
            else:
              continue


            # Calculate total for all of the legs of the flight
            matching_flights_price = 0
            for origination_destination in cancellation_details['itinerary']['originationDestinations']:
                departure_datetime = origination_destination['segments'][0]['departureDateTime'].split('.000')[0][:-3]
                departure_date = departure_datetime.split('T')[0]
                arrival_datetime = origination_destination['segments'][-1]['arrivalDateTime'].split('.000')[0][:-3]

                origin_airport = origination_destination['segments'][0]['originationAirportCode']
                destination_airport = origination_destination['segments'][-1]['destinationAirportCode']
                available = southwest.get_available_flights(
                    departure_date,
                    origin_airport,
                    destination_airport,
                    currency
                )

                # Find that the flight that matches the purchased flight
                matching_flight = next(f for f in available['trips'][0]['airProducts'] if f['segments'][0]['departureDateTime'] == departure_datetime and f['segments'][-1]['arrivalDateTime'] == arrival_datetime)
                if currency == 'Points':
                    matching_flight_price = matching_flight['fareProducts'][-1]['pointsPrice']['discountedRedemptionPoints']
                else:
                    matching_flight_price = matching_flight['fareProducts'][-1]['currencyPrice']['totalFareCents'] / 100.00
                if matching_flight_price == 0:
                    matching_flight_price = 999999
                matching_flights_price += matching_flight_price
            # Calculate refund details (current flight price - sum(current price of all legs), and print log message
            refund_amount = itinerary_price - matching_flights_price
            message = '{base_message} {currency} detected for flight {record_locator} from {origin_airport} to {destination_airport} on {departure_date}'.format(
                base_message='Price drop of {}'.format(refund_amount) if refund_amount > 0 else 'Price increase of {}'.format(refund_amount * -1),
                currency=currency,
                refund_amount=refund_amount,
                record_locator=record_locator,
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                departure_date=departure_date
            )
            logging.info(message)
            if matching_flights_price > 0 and refund_amount > 0:
                logging.info('Sending email for price drop')
                resp = requests.post(
                    'https://api.mailgun.net/v3/{}/messages'.format(settings.mailgun_domain),
                    auth=('api', settings.mailgun_api_key),
                    data={'from': 'Southwest Alerts <southwest-alerts@{}>'.format(settings.mailgun_domain),
                          'to': [email],
                          'subject': 'Southwest Price Drop Alert',
                          'text': message})
                assert resp.status_code == 200


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',stream=sys.stdout, level=logging.INFO)
    for user in settings.users:
        check_for_price_drops(user.username, user.password, user.email)
