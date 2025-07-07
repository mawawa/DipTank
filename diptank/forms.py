# diptank/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Tank # Import Tank model

class UserProfileRegistrationForm(UserCreationForm):
    name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=20, required=False)
    user_type = forms.ChoiceField(choices=UserProfile.USER_TYPE_CHOICES, required=True)
    # Add the new location_associated field for UserProfile
    location_associated = forms.CharField(
        max_length=255,
        required=False, # Make it optional for officers, required for farmers (handled in clean method)
        help_text="For farmers: the location their tanks are at."
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',) # Add email to User model fields

    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get('user_type')
        location_associated = cleaned_data.get('location_associated')

        # If user is a farmer, location_associated is required
        if user_type == 'farmer' and not location_associated:
            self.add_error('location_associated', "Farmers must specify an associated location.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'] # Save email to User model
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                name=self.cleaned_data['name'],
                email=self.cleaned_data['email'],
                phone_number=self.cleaned_data['phone_number'],
                user_type=self.cleaned_data['user_type'], # Save user_type
                location_associated=self.cleaned_data['location_associated'] # Save location_associated
            )
        return user

class TankForm(forms.ModelForm):
    class Meta:
        model = Tank
        # Removed 'owner' field from here
        fields = ['location', 'capacity', 'current_level', 'min_threshold', 'max_threshold']
        widgets = {
            'location': forms.TextInput(attrs={'placeholder': 'e.g., Farm A, Tank 1'}),
            'capacity': forms.NumberInput(attrs={'placeholder': 'e.g., 10000', 'step': 'any'}),
            'current_level': forms.NumberInput(attrs={'placeholder': 'e.g., 5000', 'step': 'any'}),
            'min_threshold': forms.NumberInput(attrs={'placeholder': 'e.g., 20', 'step': 'any'}),
            'max_threshold': forms.NumberInput(attrs={'placeholder': 'e.g., 90', 'step': 'any'}),
        }
